"""
Probe Node Sender — runs on secondary VMs (NODE_ROLE=probe).
=============================================================
Collects ICMP probe results locally and POSTs them to the primary
node's /api/ingest endpoint every PROBE_INTERVAL_SECONDS (60s).

To run on a secondary VPS:
  NODE_ROLE=probe
  NODE_ID=frankfurt-01
  NODE_REGION=eu-frankfurt-1
  NODE_LABEL=Frankfurt Node
  PRIMARY_INGEST_URL=https://your-primary-vps.com
  NODE_SECRET=your_shared_secret
  DEFAULT_HOSTS=8.8.8.8,1.1.1.1,google.com,github.com

The probe node runs the same icmp_prober code but instead of saving
to its own PostgreSQL, it ships results to the primary for correlation.
"""

import asyncio
import logging
import httpx
from datetime import datetime

from app.core.config import settings
from app.probers.icmp_prober import probe_multiple

logger = logging.getLogger("netpulse.probe_sender")


async def run_probe_and_send():
    """
    Probe all DEFAULT_HOSTS then POST batch to primary /ingest.
    Called by APScheduler every PROBE_INTERVAL_SECONDS.
    """
    if settings.NODE_ROLE != "probe":
        return  # Only runs on probe nodes

    if not settings.PRIMARY_INGEST_URL:
        logger.warning("PRIMARY_INGEST_URL not set — probe results will not be sent")
        return

    addresses = [h.strip() for h in settings.DEFAULT_HOSTS.split(",") if h.strip()]
    if not addresses:
        return

    logger.info(f"Probe node {settings.NODE_ID}: probing {len(addresses)} hosts")

    # Run probes concurrently with asyncio.gather() (Change 6)
    results = await probe_multiple(addresses)

    # Build ingest payload
    payload = {
        "node_id": settings.NODE_ID,
        "region": settings.NODE_REGION,
        "label": settings.NODE_LABEL,
        "batch_timestamp": datetime.utcnow().isoformat(),
        "results": [
            {
                "address": r.address,
                "is_reachable": r.is_reachable,
                "rtt_ms": r.rtt_ms,
                "packet_loss_pct": r.packet_loss_pct,
                "packets_sent": r.packets_sent,
                "packets_received": r.packets_received,
                "timestamp": datetime.utcnow().isoformat(),
            }
            for r in results
        ]
    }

    # POST to primary node
    url = f"{settings.PRIMARY_INGEST_URL.rstrip('/')}/api/ingest"
    headers = {"X-Node-Secret": settings.NODE_SECRET}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                f"Sent {data['accepted']} results to primary",
                extra={
                    "node": settings.NODE_ID,
                    "accepted": data["accepted"],
                    "correlations": len(data.get("correlations", [])),
                }
            )
            # Log any correlations received back
            for corr in data.get("correlations", []):
                if corr["is_local_failure"]:
                    logger.warning(
                        f"Site-local failure confirmed: {corr['target']}",
                        extra=corr
                    )
                else:
                    logger.error(
                        f"Global outage confirmed: {corr['target']}",
                        extra=corr
                    )
    except Exception as e:
        logger.error(
            f"Failed to send probe results to primary: {e}",
            extra={"url": url, "node": settings.NODE_ID}
        )
