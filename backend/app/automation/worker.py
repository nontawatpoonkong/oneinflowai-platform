"""Supervised Automation worker process and healthcheck entrypoint."""

import argparse
import asyncio
import logging
import os
import signal
import socket
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.database.session import AsyncSessionLocal
from app.models.automation import AutomationWorkerHeartbeat, AutomationWorkerState
from app.services.automation import AutomationService

logger = logging.getLogger(__name__)


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def _heartbeat_loop(
    worker_id: str,
    stop_event: asyncio.Event,
    settings: Settings,
) -> None:
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                await AutomationService(session).record_worker_heartbeat(
                    worker_id,
                    AutomationWorkerState.RUNNING,
                    build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
                )
        except Exception as exc:
            logger.error(
                "automation.worker.heartbeat_failed",
                extra={"worker_id": worker_id, "error_type": type(exc).__name__},
            )
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.AUTOMATION_WORKER_HEARTBEAT_SECONDS,
            )
        except TimeoutError:
            continue


async def run_worker(
    *,
    stop_event: asyncio.Event | None = None,
    settings: Settings | None = None,
    worker_id: str | None = None,
    max_cycles: int | None = None,
) -> None:
    settings = settings or get_settings()
    stop_event = stop_event or asyncio.Event()
    worker_id = worker_id or worker_identity()
    started_at = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        service = AutomationService(session)
        await service.record_worker_heartbeat(
            worker_id,
            AutomationWorkerState.STARTING,
            started_at=started_at,
            build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
        )
        await service.record_worker_heartbeat(
            worker_id,
            AutomationWorkerState.RUNNING,
            build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
        )
    logger.info("automation.worker.started", extra={"worker_id": worker_id})
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(worker_id, heartbeat_stop, settings)
    )
    cycles = 0
    try:
        while not stop_event.is_set():
            try:
                async with AsyncSessionLocal() as session:
                    service = AutomationService(session)
                    evaluated, executed = await service.run_once(
                        batch_size=settings.AUTOMATION_WORKER_BATCH_SIZE,
                        stale_seconds=settings.AUTOMATION_EXECUTION_STALE_SECONDS,
                        worker_id=worker_id,
                        stop_event=stop_event,
                    )
                    await service.record_worker_heartbeat(
                        worker_id,
                        AutomationWorkerState.RUNNING,
                        successful_poll=True,
                        build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
                    )
                logger.info(
                    "automation.worker.poll_succeeded",
                    extra={
                        "worker_id": worker_id,
                        "evaluated": evaluated,
                        "executed": executed,
                    },
                )
            except Exception as exc:
                logger.error(
                    "automation.worker.poll_failed",
                    extra={
                        "worker_id": worker_id,
                        "error_type": type(exc).__name__,
                    },
                )
                with suppress(Exception):
                    async with AsyncSessionLocal() as session:
                        await AutomationService(session).record_worker_heartbeat(
                            worker_id,
                            AutomationWorkerState.ERROR,
                            build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
                        )
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.AUTOMATION_WORKER_POLL_SECONDS
                )
            except TimeoutError:
                continue
    finally:
        heartbeat_stop.set()
        await heartbeat_task
        logger.info("automation.worker.shutdown", extra={"worker_id": worker_id})
        with suppress(Exception):
            async with AsyncSessionLocal() as session:
                service = AutomationService(session)
                await service.record_worker_heartbeat(
                    worker_id,
                    AutomationWorkerState.STOPPING,
                    build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
                )
                await service.record_worker_heartbeat(
                    worker_id,
                    AutomationWorkerState.STOPPED,
                    build_identifier=settings.AUTOMATION_WORKER_BUILD_IDENTIFIER,
                )


async def worker_healthcheck(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.AUTOMATION_WORKER_STALE_SECONDS
    )
    async with AsyncSessionLocal() as session:
        heartbeat = await session.scalar(
            select(AutomationWorkerHeartbeat.id)
            .where(
                AutomationWorkerHeartbeat.state == AutomationWorkerState.RUNNING.value,
                AutomationWorkerHeartbeat.last_heartbeat_at > cutoff,
            )
            .limit(1)
        )
    return heartbeat is not None


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown)
        except (NotImplementedError, RuntimeError):
            signal.signal(
                signum, lambda *_: loop.call_soon_threadsafe(request_shutdown)
            )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        return 0 if await worker_healthcheck() else 1
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    await run_worker(stop_event=stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
