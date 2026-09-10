from aiohttp import web


@web.middleware
async def admin_auth_middleware(request: web.Request, handler):
    """Protect /api/admin/* with Bearer token matching ADMIN_API_SECRET."""
    if not request.path.startswith('/api/admin'):
        return await handler(request)

    settings = request.app['settings']
    secret = settings.admin_api_secret
    if not secret:
        return web.json_response(
            {'error': 'Admin API not configured. Set ADMIN_API_SECRET.'},
            status=503,
        )

    auth = request.headers.get('Authorization', '')
    token = auth.removeprefix('Bearer ').strip()
    if not token:
        token = request.rel_url.query.get('token', '').strip()

    if token != secret:
        return web.json_response({'error': 'Unauthorized'}, status=401)

    request['admin_authenticated'] = True
    return await handler(request)
