import json
from aiohttp import web

from app.services.broadcast_admin_notify import (
    notify_broadcast_finished_if_needed,
    notify_broadcast_started,
)
from app.web.utils import parse_pagination
from app.web.services.broadcast_media import upload_broadcast_media


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


async def get_chat(request: web.Request) -> web.Response:
    raw = request.match_info['chat_id']
    try:
        chat_id = int(raw)
    except ValueError:
        return web.json_response({'error': 'Invalid chat_id'}, status=400)
    data = await request.app['admin_query'].get_chat(chat_id)
    if not data:
        return web.json_response({'error': 'Not found'}, status=404)
    return web.json_response(data)


async def bot_info(request: web.Request) -> web.Response:
    settings = request.app['settings']
    bot_info_doc = request.app.get('bot_info')
    data = await request.app['admin_query'].bot_info(settings, bot_info_doc)
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


async def _parse_broadcast_create(request: web.Request) -> tuple[dict, dict]:
    """Return (body for create_broadcast, log payload)."""
    settings = request.app['settings']
    if request.content_type and 'multipart/form-data' in request.content_type:
        reader = await request.multipart()
        fields: dict = {}
        file_bytes = None
        filename = 'upload'
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.filename:
                file_bytes = await part.read(decode=False)
                filename = part.filename
            else:
                fields[part.name] = (await part.text()) or ''
        body = {
            'target': fields.get('target', 'all_users'),
            'text': fields.get('text', ''),
        }
        if fields.get('target_id'):
            body['target_id'] = int(fields['target_id'])
        if file_bytes:
            bot = request.app.get('bot')
            admin_id = settings.super_admin_id_list[0] if settings.super_admin_id_list else 0
            if not bot or not admin_id:
                raise ValueError('Bot not available for media upload')
            caption = (fields.get('text') or '').strip() or None
            body['payload'] = await upload_broadcast_media(
                bot, admin_id, file_bytes, filename, caption=caption,
            )
            if body['payload'].get('type') != 'text':
                body['text'] = ''
        log_payload = {**body, 'media': bool(file_bytes)}
        return body, log_payload

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise ValueError('Invalid JSON')
    return body, body


async def create_broadcast(request: web.Request) -> web.Response:
    try:
        body, log_payload = await _parse_broadcast_create(request)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)

    settings = request.app['settings']
    owner_id = settings.super_admin_id_list[0] if settings.super_admin_id_list else 0

    try:
        job = await request.app['admin_query'].create_broadcast(owner_id, body)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)

    await request.app['admin_query'].log_action(
        admin_id=owner_id,
        action='broadcast_create',
        target=job.get('id', ''),
        payload=log_payload,
    )
    bot = request.app.get('bot')
    job_id = job.get('id', '')
    if bot and job_id:
        repo = request.app['admin_query'].broadcast_repo
        row = await repo.get_job(job_id) or {'_id': job_id, **job}
        await notify_broadcast_started(bot, request.app['settings'], row, owner_id)
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
    bot = request.app.get('bot')
    if bot and action == 'cancel':
        await notify_broadcast_finished_if_needed(
            bot,
            request.app['settings'],
            request.app['admin_query'].broadcast_repo,
            job_id,
        )
    return web.json_response(job)


def setup_api_routes(app: web.Application) -> None:
    app.router.add_get('/api/admin/stats', stats_overview)
    app.router.add_get('/api/admin/users', list_users)
    app.router.add_get('/api/admin/chats', list_chats)
    app.router.add_get('/api/admin/chats/{chat_id}', get_chat)
    app.router.add_get('/api/admin/bot', bot_info)
    app.router.add_get('/api/admin/join-requests', list_join_requests)
    app.router.add_get('/api/admin/broadcasts', list_broadcasts)
    app.router.add_get('/api/admin/broadcasts/{job_id}', get_broadcast)
    app.router.add_post('/api/admin/broadcasts', create_broadcast)
    app.router.add_patch('/api/admin/broadcasts/{job_id}', patch_broadcast)
