"""Super-admin mutations from the web dashboard."""

from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.core.config import Settings


class AdminActionsService:
    def __init__(self, user_repo, chat_repo, bot=None):
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.bot = bot

    async def ban_user(self, telegram_id: int, settings: Settings) -> None:
        tid = int(telegram_id)
        if tid in settings.super_admin_id_list:
            raise ValueError("Cannot ban a super admin")
        await self.user_repo.collection.update_one(
            {"telegram_id": tid},
            {
                "$set": {
                    "status": "blocked",
                    "is_active": False,
                    "platform_banned": True,
                    "banned_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            },
        )

    async def unban_user(self, telegram_id: int) -> None:
        tid = int(telegram_id)
        await self.user_repo.collection.update_one(
            {"telegram_id": tid},
            {
                "$set": {
                    "status": "active",
                    "is_active": True,
                    "platform_banned": False,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$unset": {"banned_at": ""},
            },
        )

    async def disconnect_chat(self, chat_id: int, actor_id: int = 0) -> None:
        await self.chat_repo.record_disconnect_request(int(chat_id), int(actor_id))

    async def reconnect_chat(self, chat_id: int) -> None:
        cid = int(chat_id)
        await self.chat_repo.collection.update_one(
            {"chat_id": cid},
            {
                "$set": {
                    "status": "connected",
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$unset": {
                    "disconnect_requested_by": "",
                    "disconnect_requested_at": "",
                },
            },
        )

    async def leave_chat(self, chat_id: int) -> None:
        cid = int(chat_id)
        if self.bot:
            try:
                await self.bot.leave_chat(cid)
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                raise ValueError(str(e)) from e
        await self.chat_repo.update_status(
            cid,
            "disconnected",
            {"is_active": False},
        )
