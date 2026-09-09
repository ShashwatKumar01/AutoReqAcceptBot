from aiogram import Router
from . import (
    start, tutorial, chats, settings, approval, welcome, buttons,
    broadcast, stats, join_requests, chat_member, superadmin,
    goodbye, plan, connect,
)

def setup_routers() -> Router:
    """Create main router and include all sub-routers."""
    main_router = Router()

    # Must be first or prioritized
    main_router.include_router(chat_member.router)
    main_router.include_router(join_requests.router)

    main_router.include_router(start.router)
    main_router.include_router(tutorial.router)
    main_router.include_router(chats.router)
    main_router.include_router(settings.router)
    main_router.include_router(approval.router)
    main_router.include_router(welcome.router)
    main_router.include_router(goodbye.router)
    main_router.include_router(connect.router)
    main_router.include_router(plan.router)
    main_router.include_router(buttons.router)
    main_router.include_router(broadcast.router)
    main_router.include_router(stats.router)

    # Superadmin last or as needed
    main_router.include_router(superadmin.router)

    return main_router
