"""
Change 2: Dead-man's switch — self-monitoring heartbeat system.
===============================================================
Each probe node sends a heartbeat POST to peer nodes every 30 seconds.
If a node misses 3 consecutive heartbeats (90 seconds of silence),
the surviving peer fires a "PROBE NODE DOWN" alert via Slack + email.

This means NetPulse monitors itself — zero manual health checks needed.

TECHNICAL EXPLANATION (for interviews):
  A dead-man's switch is a safety mechanism that triggers when expected
  action STOPS occurring — the opposite of a normal alert.

  Implementation:
    Probe node → POST /api/heartbeat → Primary node every 30s
    Primary checks missed_heartbeats counter every 35s (slightly longer
    than interval to allow network jitter).
    3 missed = 90s silence → node considered dead → alert fires.

  Why 3 strikes not 1:
    Single-miss alerts would fire on transient network hiccups.
    3 consecutive misses eliminates false positives from brief congestion.
    90 seconds is fast enough to detect genuine failures.

  The heartbeat endpoint records received_at timestamp and latency.
  The checker runs as an APScheduler job on the primary node.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
import httpx

from app.core.database import get_db
from app.core.config import settings
from app.models.models import ProbeNode, HeartbeatLog

logger = logging.getLogger("netpulse.heartbeat")
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class HeartbeatPayload(BaseModel):
    node_id: str
    timestamp: datetime
    region: Optional[str] = None
    uptime_seconds: Optional[float] = None


# ── Receive heartbeat ─────────────────────────────────────────────────────────

def verify_node_secret(x_node_secret: str = Header(...)):
    if x_node_secret != settings.NODE_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid node secret")
    return x_node_secret


@router.post("/heartbeat")
async def receive_heartbeat(
    payload: HeartbeatPayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_node_secret),
):
    """
    Probe nodes POST here every 30s.
    Records timestamp, resets missed_heartbeats counter, logs latency.
    """
    now = datetime.utcnow()
    latency_ms = round((now - payload.timestamp.replace(tzinfo=None)).total_seconds() * 1000, 2)

    # Update probe node record
    result = await db.execute(
        select(ProbeNode).where(ProbeNode.node_id == payload.node_id)
    )
    node = result.scalar_one_or_none()
    if node:
        node.last_heartbeat = now
        node.missed_heartbeats = 0
        node.is_active = True

    # Log heartbeat
    log = HeartbeatLog(
        node_id=payload.node_id,
        received_at=now,
        latency_ms=latency_ms,
    )
    db.add(log)
    await db.commit()

    logger.debug(
        f"Heartbeat received from {payload.node_id}",
        extra={"node": payload.node_id, "latency_ms": latency_ms}
    )
    return {"status": "ok", "latency_ms": latency_ms}


# ── Send heartbeats to peers ──────────────────────────────────────────────────

async def send_heartbeats():
    """
    APScheduler job — runs every HEARTBEAT_INTERVAL_SECONDS (30s).
    POSTs heartbeat to all peer nodes listed in PEER_NODE_URLS.
    """
    if not settings.PEER_NODE_URLS:
        return

    peer_urls = [u.strip() for u in settings.PEER_NODE_URLS.split(",") if u.strip()]
    payload = {
        "node_id": settings.NODE_ID,
        "timestamp": datetime.utcnow().isoformat(),
        "region": settings.NODE_REGION,
        "uptime_seconds": time.monotonic(),
    }
    headers = {"X-Node-Secret": settings.NODE_SECRET}

    async with httpx.AsyncClient(timeout=5.0) as client:
        for peer_url in peer_urls:
            try:
                url = f"{peer_url.rstrip('/')}/api/heartbeat"
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.debug(f"Heartbeat sent to {peer_url}")
            except Exception as e:
                logger.warning(
                    f"Heartbeat to {peer_url} failed",
                    extra={"peer": peer_url, "error": str(e)}
                )


# ── Check for missed heartbeats ───────────────────────────────────────────────

async def check_missed_heartbeats(db: AsyncSession):
    """
    APScheduler job — runs every 35 seconds on primary node.
    Checks all probe nodes for missed heartbeats.
    Fires alert after HEARTBEAT_MISS_THRESHOLD (3) consecutive misses.
    """
    threshold = timedelta(
        seconds=settings.HEARTBEAT_INTERVAL_SECONDS * settings.HEARTBEAT_MISS_THRESHOLD
    )
    cutoff = datetime.utcnow() - threshold

    result = await db.execute(
        select(ProbeNode).where(ProbeNode.is_active == True)
    )
    nodes = result.scalars().all()

    for node in nodes:
        if node.role.value == "primary":
            continue   # Don't monitor the primary node itself

        if node.last_heartbeat is None or node.last_heartbeat < cutoff:
            node.missed_heartbeats = (node.missed_heartbeats or 0) + 1

            if node.missed_heartbeats >= settings.HEARTBEAT_MISS_THRESHOLD:
                node.is_active = False
                logger.error(
                    f"PROBE NODE DOWN: {node.node_id} missed {node.missed_heartbeats} heartbeats",
                    extra={
                        "node": node.node_id,
                        "region": node.region,
                        "last_heartbeat": str(node.last_heartbeat),
                        "missed_count": node.missed_heartbeats,
                    }
                )
                await _fire_node_down_alert(node)

    await db.commit()


async def _fire_node_down_alert(node: ProbeNode):
    """Send Slack + email alert when a probe node goes silent."""
    title = f"🔴 PROBE NODE DOWN: {node.label or node.node_id}"
    description = (
        f"Node {node.node_id} ({node.region}) has missed "
        f"{node.missed_heartbeats} consecutive heartbeats "
        f"({node.missed_heartbeats * settings.HEARTBEAT_INTERVAL_SECONDS}s of silence). "
        f"Last seen: {node.last_heartbeat}"
    )
    logger.error(description)

    tasks = []
    if settings.SLACK_WEBHOOK_URL:
        tasks.append(_slack_alert(title, description))
    if settings.SMTP_USER and settings.ALERT_TO_EMAIL:
        tasks.append(_email_alert(title, description))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Node-down alert delivery failed: {r}")


async def _slack_alert(title: str, description: str):
    payload = {
        "attachments": [{
            "color": "#ff4444",
            "title": title,
            "text": description,
            "footer": "NetPulse Dead-Man's Switch",
        }]
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()


async def _email_alert(title: str, description: str):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(description, "plain")
    msg["Subject"] = title
    msg["From"] = settings.ALERT_FROM_EMAIL
    msg["To"] = settings.ALERT_TO_EMAIL

    def send():
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.ALERT_FROM_EMAIL, settings.ALERT_TO_EMAIL, msg.as_string())

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send)
