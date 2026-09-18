from typing import Optional, Dict, Any, List, Tuple
from aiogram.types import Chat as AiogramChat, User as AiogramUser, ChatMemberAdministrator

from app.database.repositories import ChatRepository, UserRepository
from app.services.telegram_service import TelegramService
from app.core.logging import get_logger
from app.core.utils import utcnow
from app.core.welcome_defaults import DEFAULT_WELCOME_TEXT
from app.services.welcome_settings_seed import seed_welcome_settings_if_missing

class ChatService:
    def __init__(
        self,
        chat_repo: ChatRepository,
        user_repo: UserRepository,
        telegram_service: TelegramService
    ):
        self.chat_repo = chat_repo
        self.user_repo = user_repo
        self.telegram_service = telegram_service
        self.logger = get_logger('chat_service')

    async def on_bot_added_as_admin(
        self,
        chat: AiogramChat,
        added_by_user: Optional[AiogramUser],
        bot_member: ChatMemberAdministrator
    ) -> Dict[str, Any]:
        """
        Called when bot becomes admin in a group/channel.
        """
        has_invite_permission = getattr(bot_member, 'can_invite_users', False)
        
        chat_data = {
            "chat_id": chat.id,
            "title": chat.title,
            "type": chat.type,
            "username": chat.username,
            "is_active": True,
            "has_join_request_permission": has_invite_permission,
            "updated_at": utcnow()
        }
        
        if added_by_user:
            chat_data["connected_by"] = added_by_user.id
            
        await self.chat_repo.upsert_chat(chat_data)
        
        await seed_welcome_settings_if_missing(self.chat_repo, chat.id)
            
        updated_chat = await self.chat_repo.get_by_chat_id(chat.id)
        return updated_chat

    async def on_bot_removed(
        self,
        chat_id: int
    ) -> None:
        """Mark chat as disconnected."""
        await self.chat_repo.update(
            {"chat_id": chat_id},
            {"is_active": False, "has_join_request_permission": False, "updated_at": utcnow()}
        )
        self.logger.info(f"Bot removed from chat {chat_id}")

    async def disconnect_chat(
        self,
        chat_id: int,
        disconnected_by: int
    ) -> bool:
        """Admin manually disconnects chat."""
        # Check permission? Assume controller did
        await self.chat_repo.update(
            {"chat_id": chat_id},
            {"is_active": False, "updated_at": utcnow()}
        )
        self.logger.info(f"Chat {chat_id} manually disconnected by {disconnected_by}")
        return True

    async def get_user_chats(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all chats connected by this user.
        Also include chats where user is an admin (from chat_admins).
        Returns list of {chat, settings} dicts.
        """
        # Simplification: return chats connected by this user
        chats = await self.chat_repo.find({"connected_by": user_id, "is_active": True})
        
        result = []
        for chat in chats:
            settings = await self.chat_repo.get_chat_settings(chat["chat_id"])
            result.append({"chat": chat, "settings": settings or {}})
            
        return result

    async def refresh_chat_permissions(
        self,
        chat_id: int
    ) -> Tuple[bool, str]:
        """
        Re-check bot permissions in the chat via Telegram API.
        Update DB.
        Returns (has_permission, reason).
        """
        has_perm, reason = await self.telegram_service.check_bot_can_approve(chat_id)
        
        await self.chat_repo.update(
            {"chat_id": chat_id},
            {"has_join_request_permission": has_perm, "updated_at": utcnow()}
        )
        
        return has_perm, reason

    async def verify_user_is_chat_admin(
        self,
        chat_id: int,
        user_id: int
    ) -> bool:
        """
        IMPORTANT: Re-verify via Telegram API, not just DB.
        Returns True if user is currently an admin of the chat.
        """
        member = await self.telegram_service.get_chat_member(chat_id, user_id)
        if not member:
            return False
            
        return member.status in ('administrator', 'creator')

    async def get_chat_with_settings(
        self,
        chat_id: int
    ) -> Optional[Dict[str, Any]]:
        """Return merged {chat, settings} dict."""
        chat = await self.chat_repo.get_by_chat_id(chat_id)
        if not chat:
            return None
            
        settings = await self.chat_repo.get_chat_settings(chat_id)
        return {"chat": chat, "settings": settings or {}}

    async def update_setting(
        self,
        chat_id: int,
        field: str,
        value: Any
    ) -> bool:
        """Update a single setting field."""
        await self.chat_repo.settings_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {field: value, "updated_at": utcnow()}},
            upsert=True
        )
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Return total, active, channel, group, disabled counts."""
        total = await self.chat_repo.collection.count_documents({})
        active = await self.chat_repo.collection.count_documents({"is_active": True})
        channel = await self.chat_repo.collection.count_documents({"type": "channel"})
        group = await self.chat_repo.collection.count_documents({"type": {"$in": ["group", "supergroup"]}})
        disabled = total - active
        
        return {
            "total": total,
            "active": active,
            "channel": channel,
            "group": group,
            "disabled": disabled
        }
