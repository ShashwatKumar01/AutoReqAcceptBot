from datetime import datetime
from typing import Any


def serialize_doc(doc: dict | None) -> dict | None:
    if not doc:
        return None
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key == '_id':
            out['id'] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, dict):
            out[key] = serialize_doc(value)
        elif isinstance(value, list):
            out[key] = [
                serialize_doc(v) if isinstance(v, dict) else
                v.isoformat() if isinstance(v, datetime) else v
                for v in value
            ]
        else:
            out[key] = value
    return out


def parse_pagination(request, default_limit: int = 25, max_limit: int = 100) -> dict:
    try:
        page = max(1, int(request.rel_url.query.get('page', '1')))
    except ValueError:
        page = 1
    try:
        limit = min(max_limit, max(1, int(request.rel_url.query.get('limit', str(default_limit)))))
    except ValueError:
        limit = default_limit
    sort = request.rel_url.query.get('sort', 'created_at')
    order = request.rel_url.query.get('order', 'desc').lower()
    direction = -1 if order == 'desc' else 1
    return {
        'page': page,
        'limit': limit,
        'skip': (page - 1) * limit,
        'sort': sort,
        'direction': direction,
        'q': request.rel_url.query.get('q', '').strip(),
        'status': request.rel_url.query.get('status', '').strip(),
        'type': request.rel_url.query.get('type', '').strip(),
        'chat_id': request.rel_url.query.get('chat_id', '').strip(),
        'owner_id': request.rel_url.query.get('owner_id', '').strip(),
    }


def broadcast_progress(job: dict) -> dict:
    sent = int(job.get('sent_count') or 0)
    failed = int(job.get('failed_count') or 0)
    total = int(job.get('total_recipients') or 0)
    done = sent + failed
    percent = round((done / total) * 100, 1) if total else 0.0
    return {
        'sent': sent,
        'failed': failed,
        'total': total,
        'done': done,
        'percent': percent,
    }
