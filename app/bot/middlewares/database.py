from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

class DatabaseMiddleware(BaseMiddleware):
    """
    Injects database repositories into handler data dict.
    Creates repository instances per update (they are stateless).
    """
    def __init__(self, db, user_repo_class, chat_repo_class, join_request_repo_class, broadcast_repo_class, subscription_repo_class, redis_client=None):
        self.db = db
        self.redis_client = redis_client
        self.user_repo_class = user_repo_class
        self.chat_repo_class = chat_repo_class
        self.join_request_repo_class = join_request_repo_class
        self.broadcast_repo_class = broadcast_repo_class
        self.subscription_repo_class = subscription_repo_class

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data['user_repo'] = self.user_repo_class(self.db)
        data['chat_repo'] = self.chat_repo_class(self.db)
        data['join_request_repo'] = self.join_request_repo_class(self.db)
        data['broadcast_repo'] = self.broadcast_repo_class(self.db)
        data['subscription_repo'] = self.subscription_repo_class(self.db)
        data['redis_client'] = self.redis_client
        data['db'] = self.db
        return await handler(event, data)
