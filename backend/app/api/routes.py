from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
import json

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import RouteTrace, Host
from app.schemas.schemas import RouteTraceOut, HopInfo

router = APIRouter()


@router.get("/", response_model=List[RouteTraceOut])
async def list_route_traces(
    host_id: int = Query(None),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(RouteTrace).order_by(desc(RouteTrace.timestamp)).limit(limit)
    if host_id:
        query = query.where(RouteTrace.host_id == host_id)
    result = await db.execute(query)
    traces = result.scalars().all()

    out = []
    for t in traces:
        hops = []
        if t.hops_json:
            try:
                hops = [HopInfo(**h) for h in json.loads(t.hops_json)]
            except Exception:
                pass
        out.append(RouteTraceOut(
            id=t.id,
            host_id=t.host_id,
            timestamp=t.timestamp,
            hop_count=t.hop_count,
            hops=hops,
            path_changed=t.path_changed,
            diff_summary=t.diff_summary,
        ))
    return out


@router.post("/{host_id}/trace")
async def trigger_trace(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Manually trigger a route trace for a host."""
    from app.probers.route_tracer import traceroute, diff_routes
    from app.models.models import RouteTrace

    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Host not found")

    trace = await traceroute(host.address)
    hops_json = trace.to_json()

    prev_result = await db.execute(
        select(RouteTrace)
        .where(RouteTrace.host_id == host_id)
        .order_by(RouteTrace.timestamp.desc())
        .limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    changed, diff_summary = False, None
    if prev and prev.hops_json:
        changed, diff_summary = diff_routes(prev.hops_json, hops_json)

    rt = RouteTrace(
        host_id=host_id,
        hop_count=trace.total_hops,
        hops_json=hops_json,
        path_changed=changed,
        diff_summary=diff_summary,
    )
    db.add(rt)
    await db.commit()
    await db.refresh(rt)

    hops = [HopInfo(**h) for h in json.loads(hops_json)]
    return RouteTraceOut(
        id=rt.id,
        host_id=rt.host_id,
        timestamp=rt.timestamp,
        hop_count=rt.hop_count,
        hops=hops,
        path_changed=rt.path_changed,
        diff_summary=rt.diff_summary,
    )
