from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from app.web.utils import serialize_doc, broadcast_progress


class AdminQueryService:
    def __init__(self, user_repo, chat_repo, join_request_repo, broadcast_repo, db):
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.join_request_repo = join_request_repo
        self.broadcast_repo = broadcast_repo
        self.db = db

    async def overview(self) -> dict:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(days=1)

        users_total = await self.user_repo.count()
        users_active = await self.user_repo.count_by_status('active')
        users_new_week = await self.user_repo.count_new_since(week_ago)
        users_new_day = await self.user_repo.count_new_since(day_ago)

        chats_total = await self.chat_repo.count()
        chats_connected = await self.chat_repo.count_by_status('connected')
        chats_channel = await self.chat_repo.count_by_type('channel')
        chats_group = await self.chat_repo.collection.count_documents(
            {"type": {"$in": ["group", "supergroup"]}}
        )

        jr = self.join_request_repo.collection
        join_total = await jr.count_documents({})
        join_approved = await jr.count_documents({"status": "approved"})
        join_pending = await jr.count_documents({"status": {"$in": ["pending", "scheduled"]}})
        join_declined = await jr.count_documents({"status": "declined"})

        bj = self.broadcast_repo.collection
        broadcast_running = await bj.count_documents({"status": "running"})
        broadcast_paused = await bj.count_documents({"status": "paused"})
        broadcast_completed = await bj.count_documents({"status": "completed"})
        broadcast_total = await bj.count_documents({})

        return {
            "users": {
                "total": users_total,
                "active": users_active,
                "new_week": users_new_week,
                "new_today": users_new_day,
            },
            "chats": {
                "total": chats_total,
                "connected": chats_connected,
                "channels": chats_channel,
                "groups": chats_group,
            },
            "join_requests": {
                "total": join_total,
                "approved": join_approved,
                "pending": join_pending,
                "declined": join_declined,
            },
            "broadcasts": {
                "total": broadcast_total,
                "running": broadcast_running,
                "paused": broadcast_paused,
                "completed": broadcast_completed,
            },
            "generated_at": now.isoformat(),
        }

    async def list_users(self, params: dict) -> dict:
        query: dict[str, Any] = {}
        q = params.get('q', '')
        if q:
            if q.isdigit():
                query['telegram_id'] = int(q)
            else:
                query['$or'] = [
                    {'username': {'$regex': q, '$options': 'i'}},
                    {'first_name': {'$regex': q, '$options': 'i'}},
                    {'last_name': {'$regex': q, '$options': 'i'}},
                ]
        if params.get('status'):
            query['status'] = params['status']

        sort_field = params.get('sort') or 'created_at'
        allowed = {'created_at', 'telegram_id', 'username', 'last_seen', 'status'}
        if sort_field not in allowed:
            sort_field = 'created_at'

        total = await self.user_repo.collection.count_documents(query)
        cursor = (
            self.user_repo.collection.find(query)
            .sort(sort_field, params['direction'])
            .skip(params['skip'])
            .limit(params['limit'])
        )
        items = [serialize_doc(d) async for d in cursor]
        return self._page(items, total, params)

    async def list_chats(self, params: dict) -> dict:
        query: dict[str, Any] = {}
        q = params.get('q', '')
        if q:
            if q.lstrip('-').isdigit():
                query['chat_id'] = int(q)
            else:
                query['title'] = {'$regex': q, '$options': 'i'}
        if params.get('status'):
            query['status'] = params['status']
        if params.get('type'):
            query['type'] = params['type']

        sort_field = params.get('sort') or 'created_at'
        allowed = {'created_at', 'title', 'chat_id', 'total_approved', 'status'}
        if sort_field not in allowed:
            sort_field = 'created_at'

        total = await self.chat_repo.collection.count_documents(query)
        cursor = (
            self.chat_repo.collection.find(query)
            .sort(sort_field, params['direction'])
            .skip(params['skip'])
            .limit(params['limit'])
        )
        items = [serialize_doc(d) async for d in cursor]
        return self._page(items, total, params)

    async def list_join_requests(self, params: dict) -> dict:
        query: dict[str, Any] = {}
        q = params.get('q', '')
        if q:
            if q.isdigit():
                num = int(q)
                query['$or'] = [{'user_id': num}, {'chat_id': num}]
            else:
                query['username'] = {'$regex': q, '$options': 'i'}
        if params.get('status'):
            query['status'] = params['status']
        if params.get('chat_id') and params['chat_id'].lstrip('-').isdigit():
            query['chat_id'] = int(params['chat_id'])

        sort_field = params.get('sort') or 'created_at'
        allowed = {'created_at', 'user_id', 'chat_id', 'status'}
        if sort_field not in allowed:
            sort_field = 'created_at'

        total = await self.join_request_repo.collection.count_documents(query)
        cursor = (
            self.join_request_repo.collection.find(query)
            .sort(sort_field, params['direction'])
            .skip(params['skip'])
            .limit(params['limit'])
        )
        items = [serialize_doc(d) async for d in cursor]
        return self._page(items, total, params)

    async def list_broadcasts(self, params: dict) -> dict:
        query: dict[str, Any] = {}
        if params.get('status'):
            query['status'] = params['status']
        if params.get('owner_id') and params['owner_id'].isdigit():
            query['owner_id'] = int(params['owner_id'])
        q = params.get('q', '')
        if q:
            query['_id'] = q

        sort_field = params.get('sort') or 'created_at'
        allowed = {'created_at', 'status', 'sent_count', 'total_recipients', 'owner_id'}
        if sort_field not in allowed:
            sort_field = 'created_at'

        total = await self.broadcast_repo.collection.count_documents(query)
        cursor = (
            self.broadcast_repo.collection.find(query)
            .sort(sort_field, params['direction'])
            .skip(params['skip'])
            .limit(params['limit'])
        )
        items = []
        async for doc in cursor:
            row = serialize_doc(doc) or {}
            row['progress'] = broadcast_progress(doc)
            items.append(row)
        return self._page(items, total, params)

    async def get_broadcast(self, job_id: str) -> dict | None:
        job = await self.broadcast_repo.get_job(job_id)
        if not job:
            return None
        row = serialize_doc(job) or {}
        row['progress'] = broadcast_progress(job)
        row['recipients'] = {
            'pending': await self.broadcast_repo.count_recipients(job_id, 'pending'),
            'sent': await self.broadcast_repo.count_recipients(job_id, 'sent'),
            'failed': await self.broadcast_repo.count_recipients(job_id, 'failed'),
        }
        return row

    async def create_broadcast(self, owner_id: int, data: dict) -> dict:
        text = (data.get('text') or '').strip()
        if not text:
            raise ValueError('text is required')

        target = data.get('target', 'all_users')
        target_id = data.get('target_id')
        job_id = str(uuid.uuid4())
        payload = {'type': 'text', 'text': text, 'parse_mode': 'HTML'}

        estimate = 0
        if target == 'chat' and target_id:
            estimate = await self.join_request_repo.collection.count_documents(
                {'chat_id': int(target_id), 'status': 'approved'}
            )
        elif target == 'all':
            chats = await self.chat_repo.get_by_admin(owner_id)
            for c in chats:
                estimate += await self.join_request_repo.collection.count_documents(
                    {'chat_id': c['chat_id'], 'status': 'approved'}
                )
        else:
            estimate = await self.user_repo.count()

        await self.broadcast_repo.create_job({
            '_id': job_id,
            'owner_id': owner_id,
            'target': target,
            'target_id': int(target_id) if target_id else None,
            'payload': payload,
            'status': 'running',
            'recipients_prepared': False,
            'sent_count': 0,
            'failed_count': 0,
            'total_recipients': estimate,
        })
        return await self.get_broadcast(job_id)

    async def broadcast_action(self, job_id: str, action: str) -> bool:
        allowed = {
            'pause': 'paused',
            'resume': 'running',
            'cancel': 'cancelled',
        }
        if action not in allowed:
            raise ValueError(f'Unknown action: {action}')
        return await self.broadcast_repo.update_job_status(job_id, allowed[action])

    async def log_action(self, admin_id: int, action: str, target: str, payload: dict) -> None:
        await self.db.admin_actions.insert_one({
            'admin_id': admin_id,
            'action': action,
            'target': target,
            'payload': payload,
            'created_at': datetime.now(timezone.utc),
        })

    @staticmethod
    def _page(items: list, total: int, params: dict) -> dict:
        limit = params['limit']
        page = params['page']
        pages = max(1, (total + limit - 1) // limit)
        return {
            'items': items,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': pages,
        }
