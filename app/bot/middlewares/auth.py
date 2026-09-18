import asyncio
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject


class AuthMiddleware(BaseMiddleware):
    """
    Injects `is_super_admin: bool` into handler data.
    Also upserts user on every private message update.
    """
    def __init__(self, super_admin_ids: list[int]):
        self.super_admin_ids = super_admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get('event_from_user')
        if user and not user.is_bot:
            is_super_admin = user.id in self.super_admin_ids
            data['is_super_admin'] = is_super_admin

            user_repo = data.get('user_repo')
            chat = data.get('event_chat')
            if user_repo:
                if not is_super_admin:
                    doc = await user_repo.get_by_telegram_id(user.id)
                    if doc and (
                        doc.get("platform_banned")
                        or doc.get("status") == "blocked"
                    ):
                        if isinstance(event, Message):
                            await event.answer(
                                "⛔ Your access to this bot has been restricted.",
                            )
                        elif isinstance(event, CallbackQuery):
                            await event.answer(
                                "Access restricted.",
                                show_alert=True,
                            )
                        return
                asyncio.create_task(
                    _safe_upsert_user(user_repo, user, chat)
                )
        else:
            data.setdefault('is_super_admin', False)

        return await handler(event, data)


async def _safe_upsert_user(user_repo, user, chat=None) -> None:
    """Upsert user silently — never raises."""
    try:
        payload = {
            "telegram_id": user.id,
            "username": user.username,
            "first_name": user.first_name or "",
            "last_name": user.last_name,
            "language_code": getattr(user, "language_code", None),
            "is_bot": False,
        }
        if chat and getattr(chat, "type", None) == ChatType.PRIVATE:
            payload["private_chat_started"] = True
        await user_repo.upsert(payload)
    except Exception:
        pass
