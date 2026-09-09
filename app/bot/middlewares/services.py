from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ServicesMiddleware(BaseMiddleware):
    """Inject shared services into handler data."""

    def __init__(self, welcome_service):
        self.welcome_service = welcome_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data['welcome_service'] = self.welcome_service
        return await handler(event, data)
