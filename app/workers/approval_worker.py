import asyncio
from datetime import datetime, timezone
from app.core.logging import get_logger


class ApprovalWorker:
    """
    Persistent worker:
    - Processes delayed approvals (every poll_interval seconds)
    - Processes delayed welcome messages (every poll_interval seconds)
    - Runs daily DB cleanup of processed join_requests (once/day at 2am UTC)
    """

    def __init__(
        self,
        approval_service,
        welcome_service,
        cleanup_service=None,
        poll_interval: int = 5,
    ):
        self.approval_service = approval_service
        self.welcome_service = welcome_service
        self.cleanup_service = cleanup_service
        self.poll_interval = poll_interval
        self.running = False
        self.logger = get_logger("approval_worker")
        self._last_cleanup_day: int = -1

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    async def start(self) -> None:
        self.running = True
        self.logger.info("APPROVAL_WORKER_STARTED", poll_interval=self.poll_interval)
        while self.running:
            try:
                now = self._utcnow()
                approvals_count = await self.approval_service.process_due_requests(now)
                if approvals_count:
                    self.logger.info("APPROVAL_WORKER_PROCESSED_APPROVALS", count=approvals_count)
                welcomes_count = await self.welcome_service.process_due_welcome_messages(now)
                if welcomes_count:
                    self.logger.info("APPROVAL_WORKER_PROCESSED_WELCOMES", count=welcomes_count)
                await self._maybe_run_daily_cleanup(now)
            except Exception as e:
                self.logger.error("APPROVAL_WORKER_ERROR", error=str(e), exc_info=True)
            await asyncio.sleep(self.poll_interval)

    async def _maybe_run_daily_cleanup(self, now: datetime) -> None:
        if not self.cleanup_service:
            return
        if now.hour == 2 and now.minute < 5:
            today = now.date().toordinal()
            if today != self._last_cleanup_day:
                self._last_cleanup_day = today
                self.logger.info("DAILY_CLEANUP_START")
                try:
                    stats = await self.cleanup_service.run_daily_cleanup()
                    self.logger.info("DAILY_CLEANUP_DONE", stats=stats)
                except Exception as e:
                    self.logger.error("DAILY_CLEANUP_FAILED", error=str(e), exc_info=True)

    async def stop(self) -> None:
        self.running = False
        self.logger.info("APPROVAL_WORKER_STOPPED")
