"""
Probe Runner — orchestrates all probers each cycle.
Called by the APScheduler every PROBE_INTERVAL_SECONDS.
"""
import logging
from datetime import datetime
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import Host, ProbeMetric, RouteTrace, ARPEntry, HostStatus
from app.probers.icmp_prober import probe_multiple
from app.probers.arp_scanner import scan_arp_table, diff_arp_tables
from app.probers.route_tracer import traceroute, diff_routes
from app.services.anomaly_detector import detector

logger = logging.getLogger("netpulse.probe_runner")

# Global ARP snapshot for diff
_last_arp_snapshot = []


async def run_all_probes():
    """Main probe cycle — runs every 60 seconds."""
    logger.info("=== Probe cycle starting ===")
    async with AsyncSessionLocal() as db:
        try:
            await _run_icmp_probes(db)
            await _run_arp_scan(db)
            await _run_route_traces(db)
        except Exception as e:
            logger.error(f"Probe cycle error: {e}", exc_info=True)
    logger.info("=== Probe cycle complete ===")


async def _run_icmp_probes(db):
    """Probe all active hosts with ICMP."""
    result = await db.execute(select(Host).where(Host.is_active == True))
    hosts = result.scalars().all()

    if not hosts:
        logger.info("No hosts to probe")
        return

    addresses = [h.address for h in hosts]
    probe_results = await probe_multiple(addresses)

    host_map = {h.address: h for h in hosts}

    for pr in probe_results:
        host = host_map.get(pr.address)
        if not host:
            continue

        # Determine host status
        if pr.is_reachable:
            if pr.packet_loss_pct > 20:
                status = HostStatus.DEGRADED
            else:
                status = HostStatus.UP
        else:
            status = HostStatus.DOWN

        host.status = status
        host.last_seen = datetime.utcnow() if pr.is_reachable else host.last_seen

        metric = ProbeMetric(
            host_id=host.id,
            rtt_ms=pr.rtt_ms,
            packet_loss_pct=pr.packet_loss_pct,
            packets_sent=pr.packets_sent,
            packets_received=pr.packets_received,
            is_reachable=pr.is_reachable,
        )
        db.add(metric)
        await db.flush()

        # Run anomaly detection
        await detector.analyse_host(db, host, metric)

    await db.commit()
    logger.info(f"ICMP probed {len(hosts)} hosts")


async def _run_arp_scan(db):
    """Scan ARP table and update topology."""
    global _last_arp_snapshot

    current = await scan_arp_table()
    if not current:
        return

    changes = diff_arp_tables(_last_arp_snapshot, current)
    _last_arp_snapshot = current

    if changes["new"]:
        logger.info(f"New devices: {[r.ip_address for r in changes['new']]}")
    if changes["disappeared"]:
        logger.info(f"Disappeared: {[r.ip_address for r in changes['disappeared']]}")
    if changes["mac_changed"]:
        logger.warning(f"MAC changed (possible ARP spoof!): {[r.ip_address for r in changes['mac_changed']]}")

    # Upsert ARP entries
    for record in current:
        result = await db.execute(
            select(ARPEntry).where(ARPEntry.ip_address == record.ip_address)
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.mac_address = record.mac_address
            entry.last_seen = datetime.utcnow()
            entry.is_active = True
            entry.state = record.state
        else:
            db.add(ARPEntry(
                ip_address=record.ip_address,
                mac_address=record.mac_address,
                interface=record.interface,
                state=record.state,
                is_active=True,
            ))

    # Mark disappeared as inactive
    for record in changes["disappeared"]:
        result = await db.execute(
            select(ARPEntry).where(ARPEntry.ip_address == record.ip_address)
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.is_active = False

    await db.commit()


async def _run_route_traces(db):
    """Run traceroute on a subset of hosts (every 5 minutes)."""
    import time
    if int(time.time()) % 300 > 60:
        return  # Only run every ~5 minutes

    result = await db.execute(
        select(Host).where(Host.is_active == True).limit(5)
    )
    hosts = result.scalars().all()

    for host in hosts:
        try:
            trace = await traceroute(host.address, max_hops=20)

            # Get previous trace for diff
            prev_result = await db.execute(
                select(RouteTrace)
                .where(RouteTrace.host_id == host.id)
                .order_by(RouteTrace.timestamp.desc())
                .limit(1)
            )
            prev_trace = prev_result.scalar_one_or_none()

            hops_json = trace.to_json()
            changed, diff_summary = False, None
            if prev_trace and prev_trace.hops_json:
                changed, diff_summary = diff_routes(prev_trace.hops_json, hops_json)
                if changed:
                    logger.warning(f"Route change for {host.address}: {diff_summary}")

            db.add(RouteTrace(
                host_id=host.id,
                hop_count=trace.total_hops,
                hops_json=hops_json,
                path_changed=changed,
                diff_summary=diff_summary,
            ))
        except Exception as e:
            logger.error(f"Traceroute failed for {host.address}: {e}")

    await db.commit()
