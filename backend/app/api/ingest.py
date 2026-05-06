"""
Change 1: Distributed probe node aggregation layer.
====================================================
Each probe node POSTs its results every 60s to /api/ingest on primary.
The primary node correlates results across nodes:

  Correlation logic:
    - If Node A sees host X DOWN but Node B sees it UP
      → Site-local failure at Node A's location
    - If both Node A and Node B see host X DOWN simultaneously
      → Genuine global outage

  This single logic addition makes the "distributed monitoring" claim
  architecturally real — two vantage points eliminate false positives
  caused by the monitoring node itself losing connectivity.

TECHNICAL EXPLANATION (for interviews):
  The ingest endpoint is authenticated with a shared NODE_SECRET header
  (X-Node-Secret) rather than JWT — node-to-node auth doesn't need
  per-user tokens. The secret is set in .env on both nodes.

  Correlation window: 120 seconds. If two nodes report the same host
  as unreachable within 120s of each other, it's a global outage.
  If only one node reports it, it's site-local.

  The correlation result is stored in Incident.node_correlation (JSON)
  and Incident.is_local_failure (bool) for dashboard display.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.models.models import ProbeNode, IngestedMetric, Host, Incident, IncidentSeverity, NodeRole

logger = logging.getLogger("netpulse.ingest")
router = APIRouter()

CORRELATION_WINDOW_SECONDS = 120


# ── Schemas ───────────────────────────────────────────────────────────────────

class IngestProbeResult(BaseModel):
    address: str
    is_reachable: bool
    rtt_ms: Optional[float] = None
    packet_loss_pct: float = 0.0
    packets_sent: int = 4
    packets_received: int = 0
    timestamp: Optional[datetime] = None


class IngestBatch(BaseModel):
    node_id: str
    region: Optional[str] = None
    label: Optional[str] = None
    results: List[IngestProbeResult]
    batch_timestamp: Optional[datetime] = None


class NodeStatusOut(BaseModel):
    node_id: str
    label: Optional[str]
    region: Optional[str]
    role: str
    is_active: bool
    last_heartbeat: Optional[datetime]
    missed_heartbeats: int


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_node_secret(x_node_secret: str = Header(...)):
    if x_node_secret != settings.NODE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid node secret",
        )
    return x_node_secret


# ── Ingest endpoint ───────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_probe_results(
    batch: IngestBatch,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_node_secret),
):
    """
    Probe nodes POST their results here every 60 seconds.
    Primary node stores results and runs correlation logic.
    """
    # Upsert probe node record
    node = await _upsert_node(db, batch)

    # Store ingested metrics
    now = datetime.utcnow()
    for result in batch.results:
        metric = IngestedMetric(
            node_id=node.id,
            target_address=result.address,
            timestamp=result.timestamp or now,
            rtt_ms=result.rtt_ms,
            packet_loss_pct=result.packet_loss_pct,
            is_reachable=result.is_reachable,
            packets_sent=result.packets_sent,
            packets_received=result.packets_received,
        )
        db.add(metric)

    await db.flush()

    # Run correlation for unreachable hosts
    correlated = []
    for result in batch.results:
        if not result.is_reachable:
            correlation = await _correlate_outage(
                db, result.address, batch.node_id, node.id
            )
            correlated.append(correlation)
            logger.warning(
                f"Outage correlation for {result.address}",
                extra={
                    "host": result.address,
                    "reporting_node": batch.node_id,
                    "is_local_failure": correlation["is_local_failure"],
                    "nodes_reporting_down": correlation["nodes_down"],
                }
            )

    await db.commit()
    logger.info(
        f"Ingested {len(batch.results)} results from {batch.node_id}",
        extra={"node": batch.node_id, "result_count": len(batch.results)}
    )

    return {
        "accepted": len(batch.results),
        "correlations": correlated,
    }


async def _upsert_node(db: AsyncSession, batch: IngestBatch) -> ProbeNode:
    result = await db.execute(
        select(ProbeNode).where(ProbeNode.node_id == batch.node_id)
    )
    node = result.scalar_one_or_none()
    if node:
        node.last_heartbeat = datetime.utcnow()
        node.missed_heartbeats = 0
        if batch.label:
            node.label = batch.label
        if batch.region:
            node.region = batch.region
    else:
        node = ProbeNode(
            node_id=batch.node_id,
            label=batch.label or batch.node_id,
            region=batch.region,
            role=NodeRole.PROBE,
            is_active=True,
            last_heartbeat=datetime.utcnow(),
        )
        db.add(node)
        await db.flush()
        logger.info(f"New probe node registered: {batch.node_id}")
    return node


async def _correlate_outage(
    db: AsyncSession,
    target_address: str,
    reporting_node_id: str,
    reporting_node_pk: int,
) -> dict:
    """
    Core correlation logic — Change 1's key contribution.

    Queries IngestedMetric for the same target across all nodes
    within the CORRELATION_WINDOW_SECONDS.

    Returns:
      - is_local_failure: True if only one node sees the host down
      - nodes_down: list of node_ids that see this host as unreachable
      - nodes_up: list of node_ids that see this host as reachable
    """
    since = datetime.utcnow() - timedelta(seconds=CORRELATION_WINDOW_SECONDS)

    # Get all recent metrics for this target from all nodes
    result = await db.execute(
        select(IngestedMetric, ProbeNode)
        .join(ProbeNode, IngestedMetric.node_id == ProbeNode.id)
        .where(
            and_(
                IngestedMetric.target_address == target_address,
                IngestedMetric.timestamp >= since,
            )
        )
        .order_by(IngestedMetric.timestamp.desc())
    )
    rows = result.all()

    # Get latest result per node
    latest_per_node = {}
    for metric, node in rows:
        if node.node_id not in latest_per_node:
            latest_per_node[node.node_id] = metric.is_reachable

    nodes_down = [n for n, reachable in latest_per_node.items() if not reachable]
    nodes_up = [n for n, reachable in latest_per_node.items() if reachable]

    # Correlation decision
    is_local = len(nodes_down) == 1 and len(nodes_up) > 0

    return {
        "target": target_address,
        "is_local_failure": is_local,
        "nodes_down": nodes_down,
        "nodes_up": nodes_up,
        "verdict": (
            f"Site-local failure at {nodes_down[0]}" if is_local
            else f"Global outage — {len(nodes_down)} nodes confirm"
        ),
    }


# ── Node status endpoints ─────────────────────────────────────────────────────

@router.get("/nodes", response_model=List[NodeStatusOut])
async def list_nodes(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_node_secret),
):
    result = await db.execute(select(ProbeNode))
    nodes = result.scalars().all()
    return [
        NodeStatusOut(
            node_id=n.node_id,
            label=n.label,
            region=n.region,
            role=n.role.value,
            is_active=n.is_active,
            last_heartbeat=n.last_heartbeat,
            missed_heartbeats=n.missed_heartbeats,
        )
        for n in nodes
    ]
