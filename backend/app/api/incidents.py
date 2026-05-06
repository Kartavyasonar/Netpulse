from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Incident
from app.schemas.schemas import IncidentOut

router = APIRouter()


@router.get("/", response_model=List[IncidentOut])
async def list_incidents(
    resolved: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Incident).order_by(desc(Incident.created_at)).limit(limit)
    if resolved is not None:
        query = query.where(Incident.is_resolved == resolved)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    from datetime import datetime
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.is_resolved = True
    incident.resolved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(incident)
    return incident
