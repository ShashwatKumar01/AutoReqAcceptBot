from pathlib import Path

from aiohttp import web

from app.web.middleware.auth import admin_auth_middleware
from app.web.routes.api import setup_api_routes
from app.web.services.admin_query import AdminQueryService

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'


async def admin_index(_request: web.Request) -> web.Response:
    index = STATIC_DIR / 'index.html'
    return web.FileResponse(index)


def setup_admin_web(app: web.Application, *, settings, user_repo, chat_repo,
                    join_request_repo, broadcast_repo, db) -> None:
    """Mount super-admin dashboard static files and REST API."""
    if not settings.admin_web_enabled:
        return

    app['settings'] = settings
    app['admin_query'] = AdminQueryService(
        user_repo=user_repo,
        chat_repo=chat_repo,
        join_request_repo=join_request_repo,
        broadcast_repo=broadcast_repo,
        db=db,
    )

    app.middlewares.insert(0, admin_auth_middleware)

    app.router.add_get('/admin/', admin_index)
    app.router.add_get('/admin', admin_index)
    app.router.add_static('/admin/assets/', STATIC_DIR, name='admin_assets')

    setup_api_routes(app)
