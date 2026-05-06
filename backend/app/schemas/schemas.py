from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from app.models.models import HostStatus, IncidentSeverity


# ── Auth ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Host ────────────────────────────────────────────────────────────────────
class HostCreate(BaseModel):
    address: str
    label: Optional[str] = None


class HostUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None


class HostOut(BaseModel):
    id: int
    address: str
    label: Optional[str]
    is_active: bool
    status: HostStatus
    last_seen: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Metrics ─────────────────────────────────────────────────────────────────
class MetricOut(BaseModel):
    id: int
    host_id: int
    timestamp: datetime
    rtt_ms: Optional[float]
    packet_loss_pct: float
    packets_sent: int
    packets_received: int
    is_reachable: bool
    tcp_port: Optional[int]
    tcp_open: Optional[bool]

    class Config:
        from_attributes = True


class MetricSummary(BaseModel):
    host_id: int
    host_address: str
    host_label: Optional[str]
    status: HostStatus
    latest_rtt_ms: Optional[float]
    latest_packet_loss_pct: Optional[float]
    avg_rtt_1h: Optional[float]
    uptime_pct_24h: Optional[float]


# ── Incidents ────────────────────────────────────────────────────────────────
class IncidentOut(BaseModel):
    id: int
    host_id: int
    severity: IncidentSeverity
    title: str
    description: Optional[str]
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    trigger_rtt_ms: Optional[float]
    trigger_packet_loss_pct: Optional[float]
    baseline_rtt_ms: Optional[float]
    sigma_deviation: Optional[float]
    email_sent: bool
    slack_sent: bool

    class Config:
        from_attributes = True


# ── Routes ───────────────────────────────────────────────────────────────────
class HopInfo(BaseModel):
    ttl: int
    ip: Optional[str]
    rtt_ms: Optional[float]
    hostname: Optional[str] = None


class RouteTraceOut(BaseModel):
    id: int
    host_id: int
    timestamp: datetime
    hop_count: Optional[int]
    hops: List[HopInfo]
    path_changed: bool
    diff_summary: Optional[str]

    class Config:
        from_attributes = True


# ── ARP / Topology ───────────────────────────────────────────────────────────
class ARPEntryOut(BaseModel):
    id: int
    ip_address: str
    mac_address: str
    interface: Optional[str]
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    state: Optional[str]

    class Config:
        from_attributes = True


class TopologyNode(BaseModel):
    id: str
    label: str
    status: str
    ip: str
    mac: Optional[str] = None
    is_gateway: bool = False


class TopologyEdge(BaseModel):
    source: str
    target: str
    label: Optional[str] = None


class TopologyGraph(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]
    timestamp: datetime


# ── Dashboard Summary ─────────────────────────────────────────────────────────
class DashboardSummary(BaseModel):
    total_hosts: int
    hosts_up: int
    hosts_down: int
    hosts_degraded: int
    active_incidents: int
    critical_incidents: int
    avg_rtt_ms: Optional[float]
    probes_last_hour: int
