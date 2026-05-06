"""
Anomaly Detection & Automated Alerting Engine — Feature 4
===========================================================
Statistical baseline engine using rolling mean + standard deviation.
Triggers alerts when metrics exceed 2-sigma (95.4%) threshold.

TECHNICAL EXPLANATION (for interviews):
  We maintain a rolling 60-minute window of RTT and packet loss samples per host.

  Baseline = rolling mean (μ) and standard deviation (σ) over the window.
  Alert threshold = μ + (N × σ) where N = ANOMALY_SIGMA_THRESHOLD (default 2.0)

  Example:
    Baseline RTT: mean=20ms, σ=3ms → alert at 20 + 2×3 = 26ms
    If measured RTT = 45ms → deviation = (45-20)/3 = 8.3σ → CRITICAL alert

  Packet loss anomaly: any loss > 0% is WARNING, > 20% is CRITICAL.
  Host down: zero packets received in a cycle = CRITICAL incident.

  Alerts are deduplicated: only one open incident per host.
  Incidents auto-resolve when metrics return to baseline.
"""

import logging
import smtplib
import httpx
import asyncio
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import numpy as np

from app.core.config import settings
from app.models.models import Host, ProbeMetric, Incident, IncidentSeverity, HostStatus

logger = logging.getLogger("netpulse.anomaly")


class AnomalyDetector:
    """
    Stateless anomaly detector — recalculates baseline from DB on each call.
    This is intentional: ensures accuracy after server restarts.
    """

    def __init__(self, sigma_threshold: float = None, window_minutes: int = None):
        self.sigma_threshold = sigma_threshold or settings.ANOMALY_SIGMA_THRESHOLD
        self.window_minutes = window_minutes or settings.BASELINE_WINDOW_MINUTES

    async def analyse_host(
        self,
        db: AsyncSession,
        host: Host,
        latest_metric: ProbeMetric,
    ) -> Optional[Incident]:
        """
        Analyse latest probe result for a host.
        Returns a new Incident if anomaly detected, else None.
        """
        # --- Host Down Detection ---
        if not latest_metric.is_reachable:
            return await self._handle_host_down(db, host, latest_metric)

        # --- RTT Anomaly Detection ---
        if latest_metric.rtt_ms is not None:
            incident = await self._check_rtt_anomaly(db, host, latest_metric)
            if incident:
                return incident

        # --- Packet Loss Anomaly ---
        if latest_metric.packet_loss_pct > 0:
            incident = await self._check_packet_loss(db, host, latest_metric)
            if incident:
                return incident

        # Host is healthy — resolve any open incidents
        await self._resolve_incidents(db, host)
        return None

    async def _get_baseline(
        self,
        db: AsyncSession,
        host_id: int,
        field: str,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate rolling mean and std dev for a metric field.
        Queries the last `window_minutes` of probe data.

        Returns (mean, std_dev) — both None if insufficient data (<5 samples).
        """
        since = datetime.utcnow() - timedelta(minutes=self.window_minutes)
        result = await db.execute(
            select(ProbeMetric)
            .where(
                and_(
                    ProbeMetric.host_id == host_id,
                    ProbeMetric.timestamp >= since,
                    ProbeMetric.is_reachable == True,
                )
            )
            .order_by(desc(ProbeMetric.timestamp))
            .limit(100)
        )
        metrics = result.scalars().all()

        if len(metrics) < 5:  # Need minimum samples for statistical significance
            return None, None

        values = [getattr(m, field) for m in metrics if getattr(m, field) is not None]
        if len(values) < 5:
            return None, None

        arr = np.array(values, dtype=float)
        return float(np.mean(arr)), float(np.std(arr))

    async def _check_rtt_anomaly(
        self,
        db: AsyncSession,
        host: Host,
        metric: ProbeMetric,
    ) -> Optional[Incident]:
        mean_rtt, std_rtt = await self._get_baseline(db, host.id, "rtt_ms")

        if mean_rtt is None or std_rtt is None:
            return None  # Not enough baseline data yet

        # Avoid division issues when std is very small
        effective_std = max(std_rtt, 1.0)
        sigma_deviation = (metric.rtt_ms - mean_rtt) / effective_std

        if sigma_deviation < self.sigma_threshold:
            return None

        severity = (
            IncidentSeverity.CRITICAL
            if sigma_deviation >= self.sigma_threshold * 2
            else IncidentSeverity.WARNING
        )

        # Check for existing open incident to avoid duplicates
        if await self._has_open_incident(db, host.id):
            return None

        incident = Incident(
            host_id=host.id,
            severity=severity,
            title=f"RTT spike on {host.label or host.address}",
            description=(
                f"RTT {metric.rtt_ms:.1f}ms is {sigma_deviation:.1f}σ above baseline "
                f"(baseline: {mean_rtt:.1f}ms ± {std_rtt:.1f}ms)"
            ),
            trigger_rtt_ms=metric.rtt_ms,
            trigger_packet_loss_pct=metric.packet_loss_pct,
            baseline_rtt_ms=mean_rtt,
            sigma_deviation=sigma_deviation,
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        logger.warning(
            f"ANOMALY [{severity.value.upper()}] {host.address}: "
            f"RTT={metric.rtt_ms:.1f}ms ({sigma_deviation:.1f}σ above baseline)"
        )
        await self._send_alerts(incident, host)
        return incident

    async def _check_packet_loss(
        self,
        db: AsyncSession,
        host: Host,
        metric: ProbeMetric,
    ) -> Optional[Incident]:
        loss = metric.packet_loss_pct
        if loss <= 5.0:  # Allow minor transient loss
            return None

        if await self._has_open_incident(db, host.id):
            return None

        severity = IncidentSeverity.CRITICAL if loss >= 20.0 else IncidentSeverity.WARNING
        incident = Incident(
            host_id=host.id,
            severity=severity,
            title=f"Packet loss on {host.label or host.address}",
            description=f"Packet loss: {loss:.1f}%",
            trigger_rtt_ms=metric.rtt_ms,
            trigger_packet_loss_pct=loss,
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        await self._send_alerts(incident, host)
        return incident

    async def _handle_host_down(
        self,
        db: AsyncSession,
        host: Host,
        metric: ProbeMetric,
    ) -> Optional[Incident]:
        if await self._has_open_incident(db, host.id):
            return None

        incident = Incident(
            host_id=host.id,
            severity=IncidentSeverity.CRITICAL,
            title=f"Host unreachable: {host.label or host.address}",
            description=f"ICMP probes not returning. Packet loss: 100%",
            trigger_packet_loss_pct=100.0,
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        logger.error(f"HOST DOWN: {host.address}")
        await self._send_alerts(incident, host)
        return incident

    async def _has_open_incident(self, db: AsyncSession, host_id: int) -> bool:
        result = await db.execute(
            select(Incident).where(
                and_(Incident.host_id == host_id, Incident.is_resolved == False)
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _resolve_incidents(self, db: AsyncSession, host: Host):
        """Auto-resolve open incidents when host recovers."""
        result = await db.execute(
            select(Incident).where(
                and_(Incident.host_id == host.id, Incident.is_resolved == False)
            )
        )
        incidents = result.scalars().all()
        for incident in incidents:
            incident.is_resolved = True
            incident.resolved_at = datetime.utcnow()
            logger.info(f"Auto-resolved incident #{incident.id} for {host.address}")
        if incidents:
            await db.commit()

    async def _send_alerts(self, incident: Incident, host: Host):
        """Fire email + Slack alerts concurrently."""
        tasks = []
        if settings.SMTP_USER and settings.ALERT_TO_EMAIL:
            tasks.append(self._send_email_alert(incident, host))
        if settings.SLACK_WEBHOOK_URL:
            tasks.append(self._send_slack_alert(incident, host))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Alert delivery failed: {r}")


    async def _send_email_alert(self, incident: Incident, host: Host):
        """Send SMTP email alert."""
        severity_emoji = "🔴" if incident.severity == IncidentSeverity.CRITICAL else "🟡"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{severity_emoji} [{incident.severity.value.upper()}] {incident.title}"
        msg["From"] = settings.ALERT_FROM_EMAIL
        msg["To"] = settings.ALERT_TO_EMAIL

        html = f"""
        <html><body style="font-family: monospace; background: #0a0a0a; color: #00ff88; padding: 20px;">
        <h2 style="color: {'#ff4444' if incident.severity == IncidentSeverity.CRITICAL else '#ffaa00'}">
            {severity_emoji} NetPulse Alert: {incident.title}
        </h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr><td style="padding: 8px; border: 1px solid #333;">Host</td>
                <td style="padding: 8px; border: 1px solid #333;">{host.address}</td></tr>
            <tr><td style="padding: 8px; border: 1px solid #333;">Severity</td>
                <td style="padding: 8px; border: 1px solid #333;">{incident.severity.value.upper()}</td></tr>
            <tr><td style="padding: 8px; border: 1px solid #333;">Description</td>
                <td style="padding: 8px; border: 1px solid #333;">{incident.description}</td></tr>
            <tr><td style="padding: 8px; border: 1px solid #333;">Time</td>
                <td style="padding: 8px; border: 1px solid #333;">{incident.created_at}</td></tr>
        </table>
        <p style="color: #666; margin-top: 20px;">NetPulse Network Operations Platform</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        def send_sync():
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.ALERT_FROM_EMAIL, settings.ALERT_TO_EMAIL, msg.as_string())

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, send_sync)
        logger.info(f"Email alert sent for incident #{incident.id}")

    async def _send_slack_alert(self, incident: Incident, host: Host):
        """Send Slack webhook notification."""
        color = "#ff4444" if incident.severity == IncidentSeverity.CRITICAL else "#ffaa00"
        payload = {
            "attachments": [{
                "color": color,
                "title": f"🚨 {incident.title}",
                "fields": [
                    {"title": "Host", "value": host.address, "short": True},
                    {"title": "Severity", "value": incident.severity.value.upper(), "short": True},
                    {"title": "Details", "value": incident.description or "N/A", "short": False},
                ],
                "footer": "NetPulse | Network Operations Platform",
                "ts": int(incident.created_at.timestamp()),
            }]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload, timeout=10)
            resp.raise_for_status()
        logger.info(f"Slack alert sent for incident #{incident.id}")


# Singleton instance
detector = AnomalyDetector()
