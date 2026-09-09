"""
RequestAcceptBot — Main Entry Point

Modes:
- Production: Webhook mode (ENVIRONMENT=production)
- Development: Long polling mode (ENVIRONMENT=development)

Workers (broadcast + approval) run in-process as background asyncio tasks
so a single Railway service handles everything.
"""
import asyncio
import os
import sys
import signal
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.connection import db_manager
from app.database.repositories import (
    UserRepository, ChatRepository, JoinRequestRepository,
    BroadcastRepository, SubscriptionRepository,
)
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.logging import LoggingMiddleware
from app.bot.middlewares.services import ServicesMiddleware
from app.bot.handlers import setup_routers
from app.services.rate_limiter import TelegramRateLimiter
from app.services.telegram_service import TelegramService
from app.services.subscription_service import SubscriptionService
from app.services.entitlement_service import EntitlementService
from app.services.approval_service import ApprovalService
from app.services.welcome_service import WelcomeService
from app.services.broadcast_service import BroadcastService
from app.workers.approval_worker import ApprovalWorker
from app.workers.broadcast_worker import BroadcastWorker


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger('main')

    # Connect DB and Redis
    await db_manager.connect(settings.mongodb_uri, settings.mongodb_database)
    await db_manager.create_indexes()
    db = db_manager.db

    redis_client = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis_client)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode='HTML'))
    bot_info = await bot.get_me()
    bot_username = bot_info.username or ""

    dp = Dispatcher(storage=storage)

    # Inject shared data
    dp['settings'] = settings
    dp['bot_username'] = bot_username

    # Register middlewares
    db_middleware = DatabaseMiddleware(
        db=db,
        user_repo_class=UserRepository,
        chat_repo_class=ChatRepository,
        join_request_repo_class=JoinRequestRepository,
        broadcast_repo_class=BroadcastRepository,
        subscription_repo_class=SubscriptionRepository,
    )
    dp.update.outer_middleware(db_middleware)
    dp.update.outer_middleware(AuthMiddleware(settings.super_admin_id_list))
    dp.update.middleware(ThrottlingMiddleware(redis_client))
    dp.update.middleware(LoggingMiddleware())

    # Build shared services (also injected into handlers)
    user_repo = UserRepository(db)
    chat_repo = ChatRepository(db)
    join_request_repo = JoinRequestRepository(db)
    broadcast_repo = BroadcastRepository(db)
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
    )
    approval_service = ApprovalService(
        join_request_repo=join_request_repo,
        chat_repo=chat_repo,
        telegram_service=telegram_service,
        welcome_service=welcome_service,
        redis_client=redis_client,
        user_repo=user_repo,
    )

    dp.update.outer_middleware(ServicesMiddleware(welcome_service))

    # Register all routers
    main_router = setup_routers()
    dp.include_router(main_router)
    broadcast_service = BroadcastService(
        broadcast_repo=broadcast_repo,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
        chat_repo=chat_repo,
        entitlement_service=entitlement_service,
        telegram_service=telegram_service,
        rate_limiter=rate_limiter,
    )

    approval_worker = ApprovalWorker(
        approval_service=approval_service,
        welcome_service=welcome_service,
        poll_interval=5,
    )
    broadcast_worker = BroadcastWorker(
        broadcast_service=broadcast_service,
        broadcast_repo=broadcast_repo,
        telegram_service=telegram_service,
        rate_limiter=rate_limiter,
        user_repo=user_repo,
        chat_repo=chat_repo,
        batch_size=getattr(settings, "broadcast_batch_size", 200),
        poll_interval=10,
    )

    # Run workers as background tasks alongside the bot
    approval_task = asyncio.create_task(approval_worker.start(), name="approval-worker")
    broadcast_task = asyncio.create_task(broadcast_worker.start(), name="broadcast-worker")
    logger.info("Background workers started: approval + broadcast")

    try:
        if settings.is_production:
            webhook_url = f"{settings.webhook_url}{settings.webhook_path}"
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True,
            )
            logger.info("Webhook set", url=webhook_url)

            app = web.Application()
            webhook_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.webhook_secret,
            )
            webhook_handler.register(app, path=settings.webhook_path)
            app.router.add_get('/health', health_check)
            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()
            # Railway injects $PORT; honor it if present, else fall back to APP_PORT.
            port = int(os.environ.get('PORT', settings.app_port))
            site = web.TCPSite(runner, host="0.0.0.0", port=port)
            logger.info(f"Starting webhook server on 0.0.0.0:{port}")
            await site.start()

            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except NotImplementedError:
                    pass
            await stop_event.wait()

            # Stop workers on shutdown
            approval_worker.running = False
            broadcast_worker.running = False
            for t in (approval_task, broadcast_task):
                t.cancel()
            await runner.cleanup()
        else:
            logger.info("Starting long polling...")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
            )

            # Stop workers on shutdown
            approval_worker.running = False
            broadcast_worker.running = False
            for t in (approval_task, broadcast_task):
                t.cancel()
    finally:
        for t in (approval_task, broadcast_task):
            if not t.done():
                t.cancel()
        await bot.session.close()
        await redis_client.aclose()
        await db_manager.disconnect()


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import logging
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
