import json
from aiohttp import web

from app.web.utils import parse_pagination


async def stats_overview(request: web.Request) -> web.Response:
    data = await request.app['admin_query'].overview()
    return web.json_response(data)


async def list_users(request: web.Request) -> web.Response:
    params = parse_pagination(request)
    data = await request.app['admin_query'].list_users(params)
    return web.json_response(data)


async def list_chats(request: web.Request) -> web.Response:
    params = parse_pagination(request)
    data = await request.app['admin_query'].list_chats(params)
    return web.json_response(data)


async def list_join_requests(request: web.Request) -> web.Response:
    params = parse_pagination(request)
    data = await request.app['admin_query'].list_join_requests(params)
    return web.json_response(data)


async def list_broadcasts(request: web.Request) -> web.Response:
    params = parse_pagination(request)
    data = await request.app['admin_query'].list_broadcasts(params)
    return web.json_response(data)


async def get_broadcast(request: web.Request) -> web.Response:
    job_id = request.match_info['job_id']
    data = await request.app['admin_query'].get_broadcast(job_id)
    if not data:
        return web.json_response({'error': 'Not found'}, status=404)
    return web.json_response(data)


async def create_broadcast(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({'error': 'Invalid JSON'}, status=400)

    owner_id = int(body.get('owner_id') or 0)
    if not owner_id:
        owner_id = request.app['settings'].super_admin_id_list[0] if request.app['settings'].super_admin_id_list else 0

    try:
        job = await request.app['admin_query'].create_broadcast(owner_id, body)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)

    await request.app['admin_query'].log_action(
        admin_id=owner_id,
        action='broadcast_create',
        target=job.get('id', ''),
        payload=body,
    )
    return web.json_response(job, status=201)


async def patch_broadcast(request: web.Request) -> web.Response:
    job_id = request.match_info['job_id']
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({'error': 'Invalid JSON'}, status=400)

    action = body.get('action', '')
    try:
        ok = await request.app['admin_query'].broadcast_action(job_id, action)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)

    if not ok:
        return web.json_response({'error': 'Job not updated'}, status=404)

    await request.app['admin_query'].log_action(
        admin_id=0,
        action=f'broadcast_{action}',
        target=job_id,
        payload=body,
    )
    job = await request.app['admin_query'].get_broadcast(job_id)
    return web.json_response(job)


def setup_api_routes(app: web.Application) -> None:
    app.router.add_get('/api/admin/stats', stats_overview)
    app.router.add_get('/api/admin/users', list_users)
    app.router.add_get('/api/admin/chats', list_chats)
    app.router.add_get('/api/admin/join-requests', list_join_requests)
    app.router.add_get('/api/admin/broadcasts', list_broadcasts)
    app.router.add_get('/api/admin/broadcasts/{job_id}', get_broadcast)
    app.router.add_post('/api/admin/broadcasts', create_broadcast)
    app.router.add_patch('/api/admin/broadcasts/{job_id}', patch_broadcast)
