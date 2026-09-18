import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from app.web.services.system_health import check_system_health
from app.services.broadcast_targets import estimate_recipients, TARGET_LABELS
from app.web.utils import serialize_doc, broadcast_progress, mask_bot_token


class AdminQueryService:
    def __init__(self, user_repo, chat_repo, join_request_repo, broadcast_repo, db, redis_client=None):
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.join_request_repo = join_request_repo
        self.broadcast_repo = broadcast_repo
        self.db = db
        self.redis_client = redis_client

    async def _system_health(self) -> dict[str, Any]:
        return await check_system_health(self.db, self.redis_client)

    async def overview(self) -> dict:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(days=1)

        jr = self.join_request_repo.collection
        bj = self.broadcast_repo.collection

        (
            users_total,
            users_active,
            users_broadcast_eligible,
            users_new_week,
            users_new_day,
            chats_total,
            chats_connected,
            chats_channel,
            chats_group,
            join_total,
            join_approved,
            join_pending,
            join_declined,
            broadcast_running,
            broadcast_paused,
            broadcast_completed,
            broadcast_total,
            system,
        ) = await asyncio.gather(
            self.user_repo.count(),
            self.user_repo.count_by_status('active'),
            self.user_repo.count_broadcast_eligible(),
            self.user_repo.count_new_since(week_ago),
            self.user_repo.count_new_since(day_ago),
            self.chat_repo.count(),
            self.chat_repo.count_by_status('connected'),
            self.chat_repo.count_by_type('channel'),
            self.chat_repo.collection.count_documents({"type": {"$in": ["group", "supergroup"]}}),
            jr.count_documents({}),
            jr.count_documents({"status": "approved"}),
            jr.count_documents({"status": {"$in": ["pending", "scheduled"]}}),
            jr.count_documents({"status": "declined"}),
            bj.count_documents({"status": "running"}),
            bj.count_documents({"status": "paused"}),
            bj.count_documents({"status": "completed"}),
            bj.count_documents({}),
            self._system_health(),
        )

        return {
            "users": {
                "total": users_total,
                "active": users_active,
                "broadcast_eligible": users_broadcast_eligible,
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
            "system": system,
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
        await self._attach_settings_summary(items)
        await self._attach_chat_broadcast_stats(items)
        return self._page(items, total, params)

    async def _attach_chat_broadcast_stats(self, items: list[dict]) -> None:
        for item in items:
            cid = item.get("chat_id")
            if cid is None:
                continue
            cid = int(cid)
            item["broadcast_eligible"] = await self.user_repo.count_broadcast_eligible(
                chat_ids=[cid],
            )
            item["tracked_members"] = await self.user_repo.count_tracked_in_chats([cid])

    async def get_chat(self, chat_id: int) -> dict | None:
        chat = await self.chat_repo.get_by_chat_id(chat_id)
        if not chat:
            return None
        settings = await self.chat_repo.get_settings_with_defaults(chat_id)
        approval = self.chat_repo.parse_approval_settings(settings)
        admin_rows = await self.chat_repo.get_admins(chat_id)
        admin_ids = sorted({int(r["user_id"]) for r in admin_rows if r.get("user_id") is not None})

        settings_out = serialize_doc(settings) or {}
        settings_out.pop("id", None)

        broadcast_eligible = await self.user_repo.count_broadcast_eligible(chat_ids=[chat_id])
        tracked_members = await self.user_repo.count_tracked_in_chats([chat_id])

        return {
            "chat": serialize_doc(chat),
            "admin_user_ids": admin_ids,
            "audience": {
                "broadcast_eligible": broadcast_eligible,
                "tracked_members": tracked_members,
            },
            "approval": approval,
            "welcome": {
                "enabled": settings.get("welcome_enabled", True),
                "trigger": settings.get("welcome_trigger", "on_approval"),
                "delay_seconds": settings.get("welcome_delay_seconds", 0),
                "frequency": settings.get("welcome_frequency", "every_join"),
                "parse_mode": settings.get("welcome_parse_mode", "HTML"),
                "text": settings.get("welcome_text", ""),
                "media_type": settings.get("welcome_media_type", ""),
                "media_file_id": settings.get("welcome_media_file_id", ""),
                "buttons": settings.get("welcome_buttons", []),
            },
            "goodbye": {
                "enabled": settings.get("goodbye_enabled", False),
                "frequency": settings.get("goodbye_frequency", "every_leave"),
                "text": settings.get("goodbye_text", ""),
                "media_type": settings.get("goodbye_media_type", ""),
                "media_file_id": settings.get("goodbye_media_file_id", ""),
                "buttons": settings.get("goodbye_buttons", []),
            },
            "settings_raw": settings_out,
        }

    async def bot_info(self, settings, bot_info: dict | None, include_token: bool = True) -> dict:
        info = bot_info or {}
        token = settings.bot_token or ""
        out = {
            "telegram": {
                "id": info.get("id"),
                "username": info.get("username"),
                "first_name": info.get("first_name"),
                "can_join_groups": info.get("can_join_groups"),
                "can_read_all_group_messages": info.get("can_read_all_group_messages"),
                "supports_inline_queries": info.get("supports_inline_queries"),
            },
            "deployment": {
                "environment": getattr(settings, "environment", None),
                "webhook_url": getattr(settings, "webhook_url", None),
                "webhook_path": getattr(settings, "webhook_path", None),
                "admin_web_url": getattr(settings, "admin_web_url", None),
            },
            "super_admin_ids": list(getattr(settings, "super_admin_id_list", []) or []),
            "token_configured": bool(token),
            "token_masked": mask_bot_token(token),
        }
        if include_token and token:
            out["bot_token"] = token
        return out

    async def _attach_settings_summary(self, items: list[dict]) -> None:
        if not items:
            return
        chat_ids = [i["chat_id"] for i in items if i.get("chat_id") is not None]
        if not chat_ids:
            return
        by_id: dict[int, dict] = {}
        cursor = self.chat_repo.settings_collection.find({"chat_id": {"$in": chat_ids}})
        async for doc in cursor:
            by_id[doc["chat_id"]] = doc
        for item in items:
            cid = item.get("chat_id")
            if cid is None:
                continue
            s = by_id.get(cid) or {}
            approval = self.chat_repo.parse_approval_settings(s)
            item["settings_summary"] = {
                "auto_approval": approval["enabled"],
                "approval_delay_seconds": approval["delay"],
                "captcha_enabled": approval["captcha_enabled"],
                "welcome_enabled": s.get("welcome_enabled", True),
                "welcome_buttons_count": len(s.get("welcome_buttons") or []),
                "goodbye_enabled": s.get("goodbye_enabled", False),
                "goodbye_buttons_count": len(s.get("goodbye_buttons") or []),
            }

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
        payload = data.get('payload')
        text = (data.get('text') or '').strip()
        if not payload:
            if not text:
                raise ValueError('Message text or media is required')
            payload = {'type': 'text', 'text': text, 'parse_mode': 'HTML'}

        target = data.get('target', 'all_users')
        target_id = data.get('target_id')
        needs_chat = target in (
            'chat', 'chat_members', 'chat_members_no_admins', 'specific_id',
        )
        if needs_chat and target_id is None:
            raise ValueError('Chat or user ID is required for this target')
        if target == 'specific_id' and target_id is None:
            raise ValueError('Telegram ID is required')

        chat_scope_owner_id = data.get('chat_scope_owner_id')
        if target in (
            'all', 'all_chat_members', 'chat_admins',
            'all_users_and_admins', 'chat_members_no_admins', 'specific_id',
        ):
            chat_scope_owner_id = None

        job_id = str(uuid.uuid4())
        estimate = await estimate_recipients(
            target,
            chat_scope_owner_id=chat_scope_owner_id,
            target_id=int(target_id) if target_id else None,
            user_repo=self.user_repo,
            chat_repo=self.chat_repo,
            join_request_repo=self.join_request_repo,
        )

        await self.broadcast_repo.create_job({
            '_id': job_id,
            'owner_id': owner_id,
            'target': target,
            'target_id': int(target_id) if target_id else None,
            'chat_scope_owner_id': chat_scope_owner_id,
            'web_created': True,
            'target_label': TARGET_LABELS.get(target, target),
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

    async def _admin_chat_map(self) -> dict[int, set[int]]:
        admin_to_chats: dict[int, set[int]] = defaultdict(set)
        async for row in self.chat_repo.admins_collection.find({}):
            uid = row.get("user_id")
            cid = row.get("chat_id")
            if uid is not None and cid is not None:
                admin_to_chats[int(uid)].add(int(cid))
        async for chat in self.chat_repo.collection.find({}, {"chat_id": 1, "admin_id": 1}):
            aid = chat.get("admin_id")
            cid = chat.get("chat_id")
            if aid is not None and cid is not None:
                admin_to_chats[int(aid)].add(int(cid))
        return admin_to_chats

    async def list_chat_admins(self, params: dict) -> dict:
        admin_map = await self._admin_chat_map()
        admin_ids = sorted(admin_map.keys())

        q = (params.get("q") or "").strip()
        if q:
            if q.isdigit():
                tid = int(q)
                admin_ids = [tid] if tid in admin_map else []
            else:
                regex = {"$regex": q, "$options": "i"}
                matched = await self.user_repo.collection.find(
                    {"$or": [{"username": regex}, {"first_name": regex}, {"last_name": regex}]},
                    {"telegram_id": 1},
                ).to_list(length=500)
                id_set = {int(d["telegram_id"]) for d in matched if d.get("telegram_id")}
                admin_ids = [i for i in admin_ids if i in id_set]

        total = len(admin_ids)
        skip = params["skip"]
        limit = params["limit"]
        page_ids = admin_ids[skip : skip + limit]

        items = []
        for uid in page_ids:
            items.append(await self._chat_admin_summary(uid, admin_map.get(uid, set())))

        return self._page(items, total, params)

    async def get_chat_admin(self, user_id: int) -> dict | None:
        admin_map = await self._admin_chat_map()
        chat_ids = admin_map.get(int(user_id))
        if not chat_ids:
            user = await self.user_repo.get_by_telegram_id(int(user_id))
            if not user:
                return None
            return await self._chat_admin_summary(int(user_id), set())
        return await self._chat_admin_summary(int(user_id), chat_ids)

    async def _chat_admin_summary(self, user_id: int, chat_ids: set[int]) -> dict:
        user = await self.user_repo.get_by_telegram_id(user_id) or {}
        ids = sorted(chat_ids)
        chats: list[dict] = []
        if ids:
            cursor = self.chat_repo.collection.find({"chat_id": {"$in": ids}})
            async for doc in cursor:
                row = serialize_doc(doc) or {}
                cid = int(row["chat_id"])
                row["broadcast_eligible"] = await self.user_repo.count_broadcast_eligible(
                    chat_ids=[cid],
                )
                row["tracked_members"] = await self.user_repo.count_tracked_in_chats([cid])
                chats.append(row)
            chats.sort(key=lambda c: (c.get("title") or "").lower())

        eligible_total = await self.user_repo.count_broadcast_eligible(chat_ids=ids) if ids else 0
        tracked_total = await self.user_repo.count_tracked_in_chats(ids) if ids else 0

        return {
            "telegram_id": user_id,
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "status": user.get("status") or "active",
            "is_active": user.get("is_active", True),
            "platform_banned": bool(user.get("platform_banned")),
            "private_chat_started": bool(user.get("private_chat_started")),
            "chat_count": len(chats),
            "broadcast_eligible_total": eligible_total,
            "tracked_members_total": tracked_total,
            "chats": chats,
        }

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
