from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Host, ProbeMetric, HostStatus
from app.schemas.schemas import MetricOut, MetricSummary, DashboardSummary

router = APIRouter()


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard_summary(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from app.models.models import Incident, IncidentSeverity

    hosts_result = await db.execute(select(Host).where(Host.is_active == True))
    hosts = hosts_result.scalars().all()

    up = sum(1 for h in hosts if h.status == HostStatus.UP)
    down = sum(1 for h in hosts if h.status == HostStatus.DOWN)
    degraded = sum(1 for h in hosts if h.status == HostStatus.DEGRADED)

    # Active incidents
    inc_result = await db.execute(
        select(func.count()).where(Incident.is_resolved == False)
    )
    active_inc = inc_result.scalar() or 0

    crit_result = await db.execute(
        select(func.count()).where(
            and_(Incident.is_resolved == False, Incident.severity == IncidentSeverity.CRITICAL)
        )
    )
    critical_inc = crit_result.scalar() or 0

    # Avg RTT from last hour
    since = datetime.utcnow() - timedelta(hours=1)
    rtt_result = await db.execute(
        select(func.avg(ProbeMetric.rtt_ms)).where(
            and_(ProbeMetric.timestamp >= since, ProbeMetric.is_reachable == True)
        )
    )
    avg_rtt = rtt_result.scalar()

    probe_count_result = await db.execute(
        select(func.count()).where(ProbeMetric.timestamp >= since)
    )
    probe_count = probe_count_result.scalar() or 0

    return DashboardSummary(
        total_hosts=len(hosts),
        hosts_up=up,
        hosts_down=down,
        hosts_degraded=degraded,
        active_incidents=active_inc,
        critical_incidents=critical_inc,
        avg_rtt_ms=round(avg_rtt, 2) if avg_rtt else None,
        probes_last_hour=probe_count,
    )


@router.get("/summary", response_model=List[MetricSummary])
async def metrics_summary(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Per-host summary with latest metrics and 24h uptime."""
    hosts_result = await db.execute(select(Host).where(Host.is_active == True))
    hosts = hosts_result.scalars().all()
    summaries = []

    since_1h = datetime.utcnow() - timedelta(hours=1)
    since_24h = datetime.utcnow() - timedelta(hours=24)

    for host in hosts:
        # Latest metric
        latest_result = await db.execute(
            select(ProbeMetric)
            .where(ProbeMetric.host_id == host.id)
            .order_by(desc(ProbeMetric.timestamp))
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        # 1h avg RTT
        avg_result = await db.execute(
            select(func.avg(ProbeMetric.rtt_ms)).where(
                and_(ProbeMetric.host_id == host.id, ProbeMetric.timestamp >= since_1h, ProbeMetric.is_reachable == True)
            )
        )
        avg_rtt = avg_result.scalar()

        # 24h uptime
        total_result = await db.execute(
            select(func.count()).where(
                and_(ProbeMetric.host_id == host.id, ProbeMetric.timestamp >= since_24h)
            )
        )
        total = total_result.scalar() or 0
        up_result = await db.execute(
            select(func.count()).where(
                and_(ProbeMetric.host_id == host.id, ProbeMetric.timestamp >= since_24h, ProbeMetric.is_reachable == True)
            )
        )
        up_count = up_result.scalar() or 0
        uptime = (up_count / total * 100) if total > 0 else None

        summaries.append(MetricSummary(
            host_id=host.id,
            host_address=host.address,
            host_label=host.label,
            status=host.status,
            latest_rtt_ms=latest.rtt_ms if latest else None,
            latest_packet_loss_pct=latest.packet_loss_pct if latest else None,
            avg_rtt_1h=round(avg_rtt, 2) if avg_rtt else None,
            uptime_pct_24h=round(uptime, 1) if uptime is not None else None,
        ))

    return summaries


@router.get("/{host_id}/timeseries", response_model=List[MetricOut])
async def host_timeseries(
    host_id: int,
    hours: int = Query(default=1, le=24),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ProbeMetric)
        .where(and_(ProbeMetric.host_id == host_id, ProbeMetric.timestamp >= since))
        .order_by(ProbeMetric.timestamp)
    )
    return result.scalars().all()
