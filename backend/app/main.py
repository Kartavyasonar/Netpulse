"""
NetPulse — Live Network Operations & Anomaly Detection Platform
FastAPI Backend Entry Point

Changes applied:
  1. Distributed ingest: /api/ingest + /api/nodes + /api/heartbeat endpoints
  2. Dead-man's switch: heartbeat checker scheduled
  3. Structured JSON logging with syslog forwarding
  4. Scapy pcap sniff() in icmp_prober (PCAP_ENABLED=true)
  5. iptables rate-limit applied on startup (Linux only)
  6. asyncio.gather() in probe_multiple() — no ThreadPoolExecutor
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging_setup import setup_logging
from app.core.database import engine, Base
from app.api import hosts, metrics, incidents, topology, routes, auth
from app.api.ingest import router as ingest_router
from app.services.heartbeat import router as heartbeat_router
from app.core.scheduler import start_scheduler, stop_scheduler

# Change 3: structured JSON logging must be first
setup_logging()

import logging
logger = logging.getLogger("netpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info(
        "NetPulse starting up",
        extra={
            "node_id": settings.NODE_ID,
            "node_role": settings.NODE_ROLE,
            "region": settings.NODE_REGION,
        }
    )

    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Change 5: apply iptables rate limit (Linux/VPS only, silently skips on Windows)
    _apply_iptables_rules()

    # Start scheduled jobs (probe cycle, heartbeat, log receiver)
    await start_scheduler()

    logger.info("NetPulse ready", extra={"role": settings.NODE_ROLE})
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await stop_scheduler()
    logger.info("NetPulse shutdown complete")


app = FastAPI(
    title="NetPulse API",
    description="Live Network Operations & Anomaly Detection Platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core API routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(hosts.router, prefix="/api/hosts", tags=["hosts"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(topology.router, prefix="/api/topology", tags=["topology"])
app.include_router(routes.router, prefix="/api/routes", tags=["routes"])

# Change 1 + 2: distributed node endpoints
app.include_router(ingest_router, prefix="/api", tags=["distributed"])
app.include_router(heartbeat_router, prefix="/api", tags=["heartbeat"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "netpulse",
        "node_id": settings.NODE_ID,
        "node_role": settings.NODE_ROLE,
        "region": settings.NODE_REGION,
    }


def _apply_iptables_rules():
    """
    Change 5: Apply iptables ICMP rate-limit rules.

    Prevents the monitoring tool from being used as an ICMP reflection amplifier.
    Rate limit: 10 packets/sec per source IP using --hashlimit module.

    Rules applied:
      1. Allow ICMP echo-request up to 10pps/source (hashlimit)
      2. DROP all other ICMP echo-requests that exceed the limit

    --hashlimit creates a per-source-IP token bucket in kernel space.
    Burst of 20 allows legitimate short spikes without triggering drops.

    Only runs on Linux — silently skips on Windows/macOS.
    """
    import platform
    import subprocess

    if platform.system() != "Linux":
        logger.info("iptables setup skipped (not Linux)")
        return

    rate = settings.IPTABLES_RATE_LIMIT
    rules = [
        # Allow ICMP up to rate/sec with burst of 20
        [
            "iptables", "-A", "INPUT",
            "-p", "icmp", "--icmp-type", "echo-request",
            "-m", "hashlimit",
            "--hashlimit-name", "icmp_rate_limit",
            "--hashlimit-upto", f"{rate}/sec",
            "--hashlimit-burst", "20",
            "--hashlimit-mode", "srcip",
            "-j", "ACCEPT",
        ],
        # DROP ICMP that exceeds rate limit
        [
            "iptables", "-A", "INPUT",
            "-p", "icmp", "--icmp-type", "echo-request",
            "-j", "DROP",
        ],
    ]

    for rule in rules:
        try:
            result = subprocess.run(
                rule, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.info(
                    f"iptables rule applied: {' '.join(rule[1:5])}",
                    extra={"rule": " ".join(rule)}
                )
            else:
                logger.warning(
                    f"iptables rule failed: {result.stderr.strip()}",
                    extra={"rule": " ".join(rule)}
                )
        except FileNotFoundError:
            logger.info("iptables not found — skipping rate limit rules")
            break
        except Exception as e:
            logger.warning(f"iptables error: {e}")
            break
