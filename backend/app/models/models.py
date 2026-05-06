"""
Database models for NetPulse.
Every table maps 1:1 to a networking concept — easy to explain in interviews.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class HostStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class IncidentSeverity(str, enum.Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class NodeRole(str, enum.Enum):
    PRIMARY = "primary"
    PROBE = "probe"


# ── Change 1: Distributed probe nodes ────────────────────────────────────────
class ProbeNode(Base):
    """
    A distributed probe node in the NetPulse network.
    Primary node aggregates results from all probe nodes.

    Correlation logic:
      - Node A (Mumbai) sees host X down, Node B (Frankfurt) sees it up
        → site-local failure at Mumbai
      - Both A and B see host X down simultaneously
        → genuine global outage
    """
    __tablename__ = "probe_nodes"

    id = Column(Integer, primary_key=True)
    node_id = Column(String(64), unique=True, nullable=False, index=True)
    label = Column(String(128), nullable=True)
    region = Column(String(64), nullable=True)
    role = Column(SAEnum(NodeRole), default=NodeRole.PROBE)
    ip_address = Column(String(45), nullable=True)
    is_active = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    missed_heartbeats = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ingested_metrics = relationship(
        "IngestedMetric", back_populates="node", cascade="all, delete-orphan"
    )


class IngestedMetric(Base):
    """
    Probe result POSTed from a remote probe node to /ingest endpoint.
    Stored separately from local ProbeMetric so correlation can compare
    results from different geographic vantage points.
    """
    __tablename__ = "ingested_metrics"

    id = Column(Integer, primary_key=True)
    node_id = Column(Integer, ForeignKey("probe_nodes.id"), nullable=False, index=True)
    target_address = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    rtt_ms = Column(Float, nullable=True)
    packet_loss_pct = Column(Float, default=0.0)
    is_reachable = Column(Boolean, default=False)
    packets_sent = Column(Integer, default=4)
    packets_received = Column(Integer, default=0)

    node = relationship("ProbeNode", back_populates="ingested_metrics")


# ── Change 2: Dead-man's switch heartbeat ────────────────────────────────────
class HeartbeatLog(Base):
    """
    Each probe node POSTs a heartbeat every 30 seconds.
    If 3 consecutive heartbeats missed (90s), surviving node fires alert.
    This makes the NOC self-monitoring — zero manual health checks needed.
    """
    __tablename__ = "heartbeat_logs"

    id = Column(Integer, primary_key=True)
    node_id = Column(String(64), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    latency_ms = Column(Float, nullable=True)


# ── Existing models ───────────────────────────────────────────────────────────
class Host(Base):
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True)
    address = Column(String(255), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    status = Column(SAEnum(HostStatus), default=HostStatus.UNKNOWN)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    metrics = relationship("ProbeMetric", back_populates="host", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="host", cascade="all, delete-orphan")
    route_traces = relationship("RouteTrace", back_populates="host", cascade="all, delete-orphan")
    arp_entries = relationship("ARPEntry", back_populates="host", cascade="all, delete-orphan")


class ProbeMetric(Base):
    """
    One probe result: RTT, packet loss, timestamp.
    Change 6: prober uses asyncio.gather() — not ThreadPoolExecutor.
    Change 4: pcap_rtt_ms captured via Scapy sniff() for delta comparison.
    """
    __tablename__ = "probe_metrics"

    id = Column(Integer, primary_key=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    rtt_ms = Column(Float, nullable=True)
    packet_loss_pct = Column(Float, default=0.0)
    packets_sent = Column(Integer, default=4)
    packets_received = Column(Integer, default=0)
    is_reachable = Column(Boolean, default=False)

    # Change 4: pcap measurement via Scapy sniff()
    pcap_rtt_ms = Column(Float, nullable=True)
    rtt_delta_ms = Column(Float, nullable=True)   # pcap_rtt - icmp_rtt

    tcp_port = Column(Integer, nullable=True)
    tcp_open = Column(Boolean, nullable=True)

    host = relationship("Host", back_populates="metrics")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False, index=True)
    severity = Column(SAEnum(IncidentSeverity), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    trigger_rtt_ms = Column(Float, nullable=True)
    trigger_packet_loss_pct = Column(Float, nullable=True)
    baseline_rtt_ms = Column(Float, nullable=True)
    sigma_deviation = Column(Float, nullable=True)

    # Change 1: node correlation
    node_correlation = Column(Text, nullable=True)    # JSON: {"mumbai":"down","frankfurt":"up"}
    is_local_failure = Column(Boolean, nullable=True) # True=site-local, False=global outage

    email_sent = Column(Boolean, default=False)
    slack_sent = Column(Boolean, default=False)

    host = relationship("Host", back_populates="incidents")


class RouteTrace(Base):
    __tablename__ = "route_traces"

    id = Column(Integer, primary_key=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    hop_count = Column(Integer, nullable=True)
    hops_json = Column(Text, nullable=True)
    path_changed = Column(Boolean, default=False)
    diff_summary = Column(Text, nullable=True)

    host = relationship("Host", back_populates="route_traces")


class ARPEntry(Base):
    __tablename__ = "arp_entries"

    id = Column(Integer, primary_key=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=True)
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False)
    interface = Column(String(50), nullable=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    state = Column(String(20), nullable=True)

    host = relationship("Host", back_populates="arp_entries")
