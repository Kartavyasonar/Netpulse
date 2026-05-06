from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Host, ARPEntry, HostStatus
from app.schemas.schemas import TopologyGraph, TopologyNode, TopologyEdge, ARPEntryOut
from app.probers.arp_scanner import get_gateway_ip
from typing import List

router = APIRouter()


@router.get("/graph", response_model=TopologyGraph)
async def get_topology(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    hosts_result = await db.execute(select(Host).where(Host.is_active == True))
    hosts = hosts_result.scalars().all()

    arp_result = await db.execute(select(ARPEntry).where(ARPEntry.is_active == True))
    arp_entries = arp_result.scalars().all()

    gateway_ip = get_gateway_ip()
    nodes: List[TopologyNode] = []
    edges: List[TopologyEdge] = []

    # Add gateway node
    nodes.append(TopologyNode(
        id="gateway",
        label=f"Gateway ({gateway_ip})" if gateway_ip else "Gateway",
        status="up",
        ip=gateway_ip or "unknown",
        is_gateway=True,
    ))

    arp_map = {e.ip_address: e for e in arp_entries}

    for host in hosts:
        status_str = host.status.value if host.status else "unknown"
        arp = arp_map.get(host.address)
        node = TopologyNode(
            id=str(host.id),
            label=host.label or host.address,
            status=status_str,
            ip=host.address,
            mac=arp.mac_address if arp else None,
        )
        nodes.append(node)
        edges.append(TopologyEdge(source="gateway", target=str(host.id)))

    # Add ARP-only nodes (discovered but not in monitored hosts)
    monitored_ips = {h.address for h in hosts}
    for entry in arp_entries:
        if entry.ip_address not in monitored_ips and entry.ip_address != gateway_ip:
            nodes.append(TopologyNode(
                id=f"arp_{entry.ip_address}",
                label=entry.ip_address,
                status="up",
                ip=entry.ip_address,
                mac=entry.mac_address,
            ))
            edges.append(TopologyEdge(source="gateway", target=f"arp_{entry.ip_address}"))

    return TopologyGraph(nodes=nodes, edges=edges, timestamp=datetime.utcnow())


@router.get("/arp", response_model=List[ARPEntryOut])
async def list_arp(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(ARPEntry).order_by(ARPEntry.last_seen.desc()))
    return result.scalars().all()
