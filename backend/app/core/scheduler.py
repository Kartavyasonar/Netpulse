"""
Background scheduler — orchestrates all periodic jobs.
Jobs differ by NODE_ROLE:
  primary: run_all_probes + check_missed_heartbeats + log_receiver
  probe:   run_probe_and_send + send_heartbeats
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.config import settings
import logging

logger = logging.getLogger("netpulse.scheduler")
scheduler = AsyncIOScheduler()


async def start_scheduler():
    if settings.NODE_ROLE == "primary":
        await _start_primary_jobs()
    else:
        await _start_probe_jobs()

    scheduler.start()
    logger.info(
        f"Scheduler started [{settings.NODE_ROLE}]",
        extra={"role": settings.NODE_ROLE, "node_id": settings.NODE_ID}
    )


async def _start_primary_jobs():
    """Jobs that run on the primary aggregator node."""
    from app.services.probe_runner import run_all_probes

    # Main ICMP probe cycle
    scheduler.add_job(
        run_all_probes,
        trigger=IntervalTrigger(seconds=settings.PROBE_INTERVAL_SECONDS),
        id="probe_all",
        name="Local Network Probe Cycle",
        replace_existing=True,
        max_instances=1,
    )

    # Change 2: check probe nodes for missed heartbeats
    from app.services.heartbeat import check_missed_heartbeats
    from app.core.database import AsyncSessionLocal

    async def _check_heartbeats():
        async with AsyncSessionLocal() as db:
            await check_missed_heartbeats(db)

    scheduler.add_job(
        _check_heartbeats,
        trigger=IntervalTrigger(seconds=settings.HEARTBEAT_INTERVAL_SECONDS + 5),
        id="check_heartbeats",
        name="Dead-Man's Switch Checker",
        replace_existing=True,
        max_instances=1,
    )

    # Change 2: also send heartbeats to peers if configured
    if settings.PEER_NODE_URLS:
        from app.services.heartbeat import send_heartbeats
        scheduler.add_job(
            send_heartbeats,
            trigger=IntervalTrigger(seconds=settings.HEARTBEAT_INTERVAL_SECONDS),
            id="send_heartbeats",
            name="Heartbeat Sender",
            replace_existing=True,
        )

    # Change 3: start log receiver thread (for probe node log shipping)
    if settings.NODE_ROLE == "primary":
        try:
            from app.core.log_receiver import start_log_receiver_thread
            start_log_receiver_thread(port=9020)
            logger.info("Log receiver started on TCP :9020")
        except Exception as e:
            logger.warning(f"Log receiver not started: {e}")

    logger.info(f"Primary jobs scheduled (probe every {settings.PROBE_INTERVAL_SECONDS}s)")


async def _start_probe_jobs():
    """Jobs that run on secondary probe nodes."""
    from app.services.probe_sender import run_probe_and_send

    # Probe and send to primary
    scheduler.add_job(
        run_probe_and_send,
        trigger=IntervalTrigger(seconds=settings.PROBE_INTERVAL_SECONDS),
        id="probe_and_send",
        name="Probe + Send to Primary",
        replace_existing=True,
        max_instances=1,
    )

    # Change 2: send heartbeats to peer/primary nodes
    from app.services.heartbeat import send_heartbeats
    scheduler.add_job(
        send_heartbeats,
        trigger=IntervalTrigger(seconds=settings.HEARTBEAT_INTERVAL_SECONDS),
        id="send_heartbeats",
        name="Heartbeat Sender",
        replace_existing=True,
    )

    logger.info(f"Probe node jobs scheduled → {settings.PRIMARY_INGEST_URL}")


async def stop_scheduler():
    scheduler.shutdown(wait=False)
