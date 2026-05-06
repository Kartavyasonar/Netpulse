from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Host
from app.schemas.schemas import HostCreate, HostOut, HostUpdate
from app.core.config import settings

router = APIRouter()


@router.get("/", response_model=List[HostOut])
async def list_hosts(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Host).order_by(Host.created_at))
    return result.scalars().all()


@router.post("/", response_model=HostOut)
async def create_host(body: HostCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    existing = await db.execute(select(Host).where(Host.address == body.address))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Host already exists")
    host = Host(address=body.address, label=body.label)
    db.add(host)
    await db.commit()
    await db.refresh(host)
    return host


@router.patch("/{host_id}", response_model=HostOut)
async def update_host(host_id: int, body: HostUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    if body.label is not None:
        host.label = body.label
    if body.is_active is not None:
        host.is_active = body.is_active
    await db.commit()
    await db.refresh(host)
    return host


@router.delete("/{host_id}")
async def delete_host(host_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    await db.delete(host)
    await db.commit()
    return {"deleted": host_id}


@router.post("/seed")
async def seed_default_hosts(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Seed the database with default hosts from config."""
    addresses = [h.strip() for h in settings.DEFAULT_HOSTS.split(",") if h.strip()]
    added = []
    for addr in addresses:
        existing = await db.execute(select(Host).where(Host.address == addr))
        if not existing.scalar_one_or_none():
            host = Host(address=addr, label=addr)
            db.add(host)
            added.append(addr)
    await db.commit()
    return {"added": added}
