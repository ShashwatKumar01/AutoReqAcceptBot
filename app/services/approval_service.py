from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from aiogram.types import ChatJoinRequest
from redis.asyncio import Redis

from app.database.repositories import JoinRequestRepository, ChatRepository
from app.services.telegram_service import TelegramService
from app.core.logging import get_logger
from app.core.utils import utcnow, generate_job_id

class ApprovalService:
    def __init__(
        self,
        join_request_repo: JoinRequestRepository,
        chat_repo: ChatRepository,
        telegram_service: TelegramService,
        welcome_service: Any,  # forward ref
        redis_client: Redis,
        user_repo: Any = None,
    ):
        self.join_request_repo = join_request_repo
        self.chat_repo = chat_repo
        self.telegram_service = telegram_service
        self.welcome_service = welcome_service
        self.redis = redis_client
        self.user_repo = user_repo
        self.logger = get_logger('approval_service')

    async def handle_new_join_request(
        self,
        join_request: ChatJoinRequest
    ) -> None:
        """
        Called by handler when a new ChatJoinRequest arrives.
        """
        chat_id = join_request.chat.id
        user_id = join_request.from_user.id
        
        request_doc = await self.join_request_repo.create_request(chat_id, user_id)
        if not request_doc:
            self.logger.info(f"Duplicate/handled request {chat_id}:{user_id}")
            return
            
        approval = await self.chat_repo.get_approval_settings(chat_id)
        settings = await self.chat_repo.get_chat_settings_with_defaults(chat_id)
            
        if approval["enabled"]:
            delay = approval["delay"]
            if delay == 0:
                await self.execute_approval(request_doc["_id"], request_doc, settings)
            else:
                schedule_time = utcnow() + timedelta(seconds=delay)
                await self.join_request_repo.update(
                    {"_id": request_doc["_id"]},
                    {"status": "scheduled", "scheduled_at": schedule_time},
                )
                self.logger.info(f"Scheduled approval for {chat_id}:{user_id} at {schedule_time}")
                
        if settings.get("welcome_enabled", True) and settings.get("welcome_trigger") == "on_request":
            if self.welcome_service:
                await self.welcome_service.handle_join_request(
                    user_id=user_id,
                    chat_id=chat_id,
                    from_user=join_request.from_user,
                    request_doc=request_doc,
                )

    async def execute_approval(
        self,
        request_id: str,
        request_doc: Dict[str, Any],
        settings: Dict[str, Any]
    ) -> bool:
        """
        Actually approve the request via Telegram API.
        Uses Redis distributed lock to prevent duplicate processing.
        """
        lock_key = f"lock:approve:{request_id}"
        if not await self._acquire_lock(lock_key):
            return False
            
        try:
            current_doc = await self.join_request_repo.get(request_id)
            if not current_doc or current_doc.get("status") not in ("pending", "scheduled"):
                return True
                
            success = await self.telegram_service.approve_join_request(
                chat_id=request_doc["chat_id"],
                user_id=request_doc["user_id"]
            )
            
            if success:
                await self.join_request_repo.update(
                    {"_id": request_id},
                    {"status": "approved", "processed_at": utcnow()}
                )

                if self.user_repo:
                    try:
                        await self.user_repo.upsert({
                            "telegram_id": request_doc["user_id"],
                            "username": request_doc.get("username"),
                            "first_name": request_doc.get("first_name"),
                            "last_name": request_doc.get("last_name"),
                            "is_bot": False,
                            "is_active": True,
                            "chat_id": request_doc["chat_id"],
                        })
                        await self.chat_repo.increment_counter(
                            request_doc["chat_id"], "total_join_requests"
                        )
                        await self.chat_repo.increment_counter(
                            request_doc["chat_id"], "total_approved"
                        )
                    except Exception as e:
                        self.logger.warning(
                            "User upsert failed after delayed approval",
                            error=str(e),
                        )
                
                if self.welcome_service and settings.get("welcome_enabled", True):
                    await self.welcome_service.handle_approval(
                        user_id=request_doc["user_id"],
                        chat_id=request_doc["chat_id"],
                        from_user=_DictUser(
                            id=request_doc["user_id"],
                            first_name=request_doc.get("first_name", ""),
                            last_name=request_doc.get("last_name"),
                            username=request_doc.get("username"),
                        ),
                        request_doc=current_doc,
                    )
                    
                return True
            else:
                await self.join_request_repo.update(
                    {"_id": request_id},
                    {"status": "failed", "processed_at": utcnow()}
                )
                return False
                
        finally:
            await self._release_lock(lock_key)

    async def process_due_requests(
        self,
        now: datetime
    ) -> int:
        """
        Fetches all due scheduled requests. Processes each one with locking.
        """
        due_requests = await self.join_request_repo.find({
            "status": "scheduled",
            "scheduled_at": {"$lte": now}
        })
        
        count = 0
        for req in due_requests:
            settings = await self.chat_repo.get_chat_settings_with_defaults(req["chat_id"])
            if await self.execute_approval(req["_id"], req, settings):
                count += 1
                    
        return count

    async def _acquire_lock(
        self, key: str, ttl: int = 60
    ) -> bool:
        """Acquire Redis distributed lock."""
        return await self.redis.set(key, "locked", nx=True, ex=ttl)

    async def _release_lock(self, key: str) -> None:
        """Release Redis lock."""
        await self.redis.delete(key)


class _DictUser:
    def __init__(self, id: int, first_name: str, last_name=None, username=None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
