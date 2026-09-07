"""
Broadcast Worker Entry Point
Run: python workers/run_broadcast_worker.py
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
    BroadcastRepository, UserRepository, JoinRequestRepository,
    ChatRepository, SubscriptionRepository
)
from app.services.rate_limiter import TelegramRateLimiter
from app.services.telegram_service import TelegramService
from app.services.subscription_service import SubscriptionService
from app.services.entitlement_service import EntitlementService
from app.services.broadcast_service import BroadcastService
from app.workers.broadcast_worker import BroadcastWorker
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from redis.asyncio import Redis


async def main():
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger('run_broadcast_worker')
    logger.info("Initializing Broadcast Worker Process...")

    await db_manager.connect(settings.mongodb_uri, settings.mongodb_database)
    await db_manager.create_indexes()
    db = db_manager.db

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode='HTML'))

    broadcast_repo = BroadcastRepository(db)
    join_request_repo = JoinRequestRepository(db)
    user_repo = UserRepository(db)
    chat_repo = ChatRepository(db)
    subscription_repo = SubscriptionRepository(db)

    await subscription_repo.seed_default_plans()

    rate_limiter = TelegramRateLimiter(redis_client)
    telegram_service = TelegramService(bot, rate_limiter)
    subscription_service = SubscriptionService(subscription_repo)
    entitlement_service = EntitlementService(subscription_service)

    broadcast_service = BroadcastService(
        broadcast_repo=broadcast_repo,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
        chat_repo=chat_repo,
        entitlement_service=entitlement_service,
        telegram_service=telegram_service,
        rate_limiter=rate_limiter,
    )

    worker = BroadcastWorker(
        broadcast_service=broadcast_service,
        broadcast_repo=broadcast_repo,
        telegram_service=telegram_service,
        rate_limiter=rate_limiter,
        user_repo=user_repo,
        chat_repo=chat_repo,
        batch_size=settings.broadcast_batch_size,
        poll_interval=10,
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

    logger.info("Starting Broadcast Worker...")
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
    logger.info("Broadcast Worker shut down.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
