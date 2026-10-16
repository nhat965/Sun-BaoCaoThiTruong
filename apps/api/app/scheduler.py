"""Production scheduler built on the existing database-backed job lease kernel.

The module is deliberately independent from FastAPI lifespan. It can run once in a
cron/container or continuously as the dedicated worker process.
"""

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.automation import AutomationService, job_schema
from app.config import Settings
from app.data_pipeline import DataSyncService, provider_catalog
from app.database import JobRecord, SecurityRecord, SessionLocal
from app.market_reporting import build_market_overview, create_daily_market_report

logger = logging.getLogger(__name__)

JOB_TYPES = (
    "SYNC_SECURITIES_MASTER",
    "SYNC_OHLCV",
    "SYNC_MARKET_INDICES",
    "SYNC_FINANCIAL_STATEMENTS",
    "RECALCULATE_MARKET_INTELLIGENCE",
    "GENERATE_DAILY_REPORT",
    "CHECK_PROVIDER_HEALTH",
)
MARKET_SCOPE = "market"


class SchedulerBlocked(RuntimeError):
    """A known missing entitlement/source; do not retry indefinitely."""

    def __init__(self, message: str, code: str = "provider_blocked"):
        super().__init__(message)
        self.code = code


class ProductionScheduler:
    def __init__(self, settings: Settings, *, worker_id: str | None = None):
        self.settings = settings
        self.zone = ZoneInfo(settings.market_timezone)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.automation = AutomationService(
            None,
            settings.automation_max_retries,
            settings.automation_lease_seconds,
            settings.market_timezone,
        )

    def _times(self) -> list[time]:
        values: list[time] = []
        for raw in self.settings.scheduler_daily_times.split(","):
            try:
                hour, minute = (int(part) for part in raw.strip().split(":", 1))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    values.append(time(hour, minute))
            except (TypeError, ValueError):
                logger.warning("Ignoring invalid scheduler time configuration")
        return values or [time(16, 30)]

    def current_slot(self, now: datetime | None = None) -> datetime:
        local = (now or datetime.now(UTC)).astimezone(self.zone)
        slot = max((time_value for time_value in self._times() if time_value <= local.time()), default=self._times()[0])
        slot_date = local.date() if any(value <= local.time() for value in self._times()) else date.fromordinal(local.date().toordinal() - 1)
        return datetime.combine(slot_date, slot, tzinfo=self.zone).astimezone(UTC).replace(second=0, microsecond=0)

    def enqueue_due(self, now: datetime | None = None) -> list[JobRecord]:
        """Enqueue one idempotent batch for the current configured slot."""
        current = (now or datetime.now(UTC)).astimezone(self.zone)
        slot = self.current_slot(now)
        if current.weekday() >= 5:
            # There is no official trading session on weekends; health checks remain useful.
            types = ("CHECK_PROVIDER_HEALTH",)
        else:
            types = JOB_TYPES
        jobs: list[JobRecord] = []
        def add(job_type: str, symbol: str = "__MARKET__", provider: str | None = "auto"):
            if len(jobs) >= self.settings.scheduler_batch_limit:
                return
            key = f"{job_type}:{symbol}:{slot.isoformat()}"
            jobs.append(self.automation.enqueue_job(
                job_type, symbol=symbol, scheduled_for=slot,
                provider=provider, scope=MARKET_SCOPE if symbol == "__MARKET__" else "security",
                idempotency_key=key,
            ))

        with SessionLocal() as session:
            symbols = list(session.scalars(
                select(SecurityRecord.symbol)
                .where(SecurityRecord.listing_status == "active", SecurityRecord.security_type == "stock")
                .order_by(SecurityRecord.symbol)
            ).all())
        for job_type in types:
            if job_type in {"SYNC_OHLCV", "SYNC_FINANCIAL_STATEMENTS"}:
                for symbol in symbols:
                    add(job_type, symbol, "auto" if job_type == "SYNC_OHLCV" else "authorized_file")
            else:
                add(job_type)
        return jobs

    async def run_once(self, job_id: int) -> dict:
        lease = self.automation.claim(job_id, worker_id=self.worker_id)
        if lease is None:
            with SessionLocal() as session:
                row = session.get(JobRecord, job_id)
                return {"claimed": False, "job": job_schema(row) if row else None}
        with SessionLocal() as session:
            row = session.get(JobRecord, job_id)
            job_type = row.job_type
            provider = row.provider or "auto"
            symbol = row.symbol
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(lease))
        try:
            result = await self._execute(job_type, symbol, provider)
            if result.get("status") == "PARTIAL":
                row = self.automation.complete_partial(lease, result)
            else:
                row = self.automation.complete_success(lease, result)
        except SchedulerBlocked as exc:
            row = self.automation.complete_blocked(lease, str(exc), error_code=exc.code)
        except Exception as exc:
            logger.exception("scheduler job failed", extra={"job_id": job_id, "job_type": job_type})
            row = self.automation.complete_failure(lease, f"{type(exc).__name__}: {exc}")
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        return {"claimed": True, "job": job_schema(row)}

    async def _heartbeat_loop(self, lease) -> None:
        interval = max(1, self.settings.automation_lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            if not self.automation.heartbeat(lease):
                return

    async def _execute(self, job_type: str, symbol: str, provider: str) -> dict:
        if job_type == "SYNC_OHLCV":
            run = await DataSyncService(self.settings).sync_prices(symbol, provider_id=provider, requested_mode="incremental")
            return self._sync_result(run)
        if job_type == "SYNC_FINANCIAL_STATEMENTS":
            run = DataSyncService(self.settings).sync_financials(symbol)
            if run.status == "BLOCKED":
                raise SchedulerBlocked(run.error_message or "Financial provider is blocked")
            return self._sync_result(run)
        if job_type == "CHECK_PROVIDER_HEALTH":
            statuses = provider_catalog(self.settings)
            blocked = sum(item.availability == "blocked" for item in statuses)
            return {"status": "PARTIAL" if blocked else "SUCCESS", "provider_count": len(statuses), "blocked_count": blocked, "source_freshness": "diagnostic"}
        if job_type == "SYNC_SECURITIES_MASTER":
            raise SchedulerBlocked("No authorized securities-master provider is configured", "securities_provider_blocked")
        if job_type == "SYNC_MARKET_INDICES":
            raise SchedulerBlocked("No authorized market-index provider is configured", "index_provider_blocked")
        if job_type == "RECALCULATE_MARKET_INTELLIGENCE":
            overview = build_market_overview()
            if overview.status == "unavailable":
                raise SchedulerBlocked("Market analytics unavailable because upstream coverage is insufficient", "upstream_incomplete")
            return {"status": overview.status, "coverage_percent": overview.coverage_percent, "source_freshness": overview.source_mode}
        if job_type == "GENERATE_DAILY_REPORT":
            overview = build_market_overview()
            if overview.status == "unavailable":
                raise SchedulerBlocked("Daily report withheld: upstream market data is unavailable", "upstream_incomplete")
            report = create_daily_market_report("post_market", overview.as_of.date() if overview.as_of else None)
            return {"snapshot_key": report.snapshot_key, "source_freshness": report.source_mode}
        raise ValueError(f"Unsupported scheduler job type: {job_type}")

    @staticmethod
    def _sync_result(run) -> dict:
        return {
            "status": run.status,
            "inserted_count": run.inserted_count,
            "updated_count": run.updated_count,
            "skipped_count": run.skipped_count,
            "error_count": run.error_count,
            "cursor_from": run.cursor_from,
            "cursor_to": run.cursor_to,
            "source_freshness": run.details.get("source_mode") or run.details.get("validation_status"),
        }

    async def run_pending(self, *, limit: int | None = None) -> list[dict]:
        limit = limit or self.settings.scheduler_batch_limit
        now = datetime.now(UTC)
        with SessionLocal() as session:
            jobs = list(session.scalars(
                select(JobRecord).where(
                    or_(JobRecord.status == "QUEUED", JobRecord.status == "RETRY_PENDING"),
                    or_(JobRecord.next_attempt_at.is_(None), JobRecord.next_attempt_at <= now),
                ).order_by(JobRecord.id).limit(limit)
            ).all())
            ids = [job.id for job in jobs if self._dependencies_ready(session, job)]
        semaphore = asyncio.Semaphore(max(1, self.settings.scheduler_max_concurrency))
        async def run_limited(job_id: int):
            async with semaphore:
                return await self.run_once(job_id)
        return await asyncio.gather(*(run_limited(job_id) for job_id in ids))

    @staticmethod
    def _dependencies_ready(session, job: JobRecord) -> bool:
        """Do not let analytics/report jobs race their upstream sync jobs."""
        required: tuple[str, ...] = ()
        if job.job_type == "RECALCULATE_MARKET_INTELLIGENCE":
            required = ("SYNC_SECURITIES_MASTER", "SYNC_OHLCV", "SYNC_MARKET_INDICES")
        elif job.job_type == "GENERATE_DAILY_REPORT":
            required = ("RECALCULATE_MARKET_INTELLIGENCE",)
        if not required:
            return True
        rows = list(session.scalars(select(JobRecord).where(JobRecord.scheduled_for == job.scheduled_for)).all())
        for job_type in required:
            selected = [row for row in rows if row.job_type == job_type]
            if not selected or any(row.status in {"QUEUED", "RUNNING", "RETRY_PENDING"} for row in selected):
                return False
        return True

    async def run_cycle(self, now: datetime | None = None) -> dict:
        enqueued = self.enqueue_due(now)
        results = await self.run_pending()
        return {"enqueued": len(enqueued), "processed": len(results), "results": results}

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            await self.run_cycle()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=max(1, self.settings.scheduler_poll_interval_seconds))
            except TimeoutError:
                pass
