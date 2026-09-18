"""
Approval Worker Entry Point
Run: python workers/run_approval_worker.py
"""
import asyncio
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.connection import db_manager
from app.database.repositories import (
    JoinRequestRepository, ChatRepository, UserRepository, SubscriptionRepository
)
from app.services.rate_limiter import TelegramRateLimiter
from app.services.telegram_service import TelegramService
from app.services.welcome_service import WelcomeService
from app.services.subscription_service import SubscriptionService
from app.services.entitlement_service import EntitlementService
from app.services.approval_service import ApprovalService
from app.workers.approval_worker import ApprovalWorker
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from redis.asyncio import Redis


async def main():
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger('run_approval_worker')
    logger.info("Initializing Approval Worker Process...")

    await db_manager.connect(settings.mongodb_uri, settings.mongodb_database)
    await db_manager.create_indexes()
    db = db_manager.db

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode='HTML'))

    join_request_repo = JoinRequestRepository(db)
    chat_repo = ChatRepository(db)
    user_repo = UserRepository(db)
    subscription_repo = SubscriptionRepository(db)

    await subscription_repo.seed_default_plans()

    rate_limiter = TelegramRateLimiter(redis_client)
    telegram_service = TelegramService(bot, rate_limiter)
    subscription_service = SubscriptionService(subscription_repo)
    entitlement_service = EntitlementService(subscription_service)

    welcome_service = WelcomeService(
        chat_repo=chat_repo,
        telegram_service=telegram_service,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
    )
    approval_service = ApprovalService(
        join_request_repo=join_request_repo,
        chat_repo=chat_repo,
        telegram_service=telegram_service,
        welcome_service=welcome_service,
        redis_client=redis_client,
    )

    worker = ApprovalWorker(
        approval_service=approval_service,
        welcome_service=welcome_service,
        poll_interval=settings.approval_poll_interval,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal(sig):
        logger.info(f"Received exit signal {sig.name}...")
        loop.create_task(worker.stop())
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            pass

    logger.info("Starting Approval Worker...")
    worker_task = asyncio.create_task(worker.start())
    await stop_event.wait()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    await bot.session.close()
    await redis_client.aclose()
    await db_manager.disconnect()
    logger.info("Approval Worker shut down.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
