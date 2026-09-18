from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db['users']

    async def upsert(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        telegram_id = user_data['telegram_id']
        now = datetime.now(timezone.utc)

        # If a chat_id is provided, also track it on the user so
        # broadcast can target users by chat.
        chat_id = user_data.pop('chat_id', None)
        private_chat = user_data.pop('private_chat_started', None)

        fields = {k: v for k, v in user_data.items() if k != 'telegram_id'}
        update_doc = {
            "$set": fields,
            "$setOnInsert": {"created_at": now},
        }
        if private_chat is True:
            update_doc["$set"]["private_chat_started"] = True
        if chat_id is not None:
            update_doc["$addToSet"] = {"chat_ids": int(chat_id)}

        return await self.collection.find_one_and_update(
            {"telegram_id": telegram_id},
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"telegram_id": telegram_id})

    async def update_status(self, telegram_id: int, status: str) -> bool:
        result = await self.collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def count_total(self) -> int:
        return await self.collection.count_documents({})

    async def count_broadcast_eligible(self, *, chat_ids: list[int] | None = None) -> int:
        """Users who opened the bot in DM (/start) and can receive broadcasts."""
        query: Dict[str, Any] = {"private_chat_started": True}
        if chat_ids is not None:
            if not chat_ids:
                return 0
            query["chat_ids"] = {"$in": [int(c) for c in chat_ids]}
        return await self.collection.count_documents(query)

    async def count_tracked_in_chats(self, chat_ids: list[int]) -> int:
        """Users stored for these chats (may not have started DM yet)."""
        if not chat_ids:
            return 0
        return await self.collection.count_documents(
            {"chat_ids": {"$in": [int(c) for c in chat_ids]}},
        )

    async def count(self) -> int:
        return await self.count_total()

    async def update(self, filter: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Generic update used by services: forwards $set / $inc as-is."""
        if not any(k.startswith('$') for k in update.keys()):
            update = {"$set": {**update, "updated_at": datetime.now(timezone.utc)}}
        else:
            if '$set' in update:
                update['$set'] = {**update['$set'], 'updated_at': datetime.now(timezone.utc)}
        result = await self.collection.update_one(filter, update)
        return result.modified_count > 0

    async def count_by_status(self, status: str) -> int:
        return await self.collection.count_documents({"status": status})

    async def count_new_since(self, since: datetime) -> int:
        return await self.collection.count_documents({"created_at": {"$gte": since}})

    async def get_all_eligible_for_broadcast(self, skip: int, limit: int) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"status": "active"}).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_last_seen(self, telegram_id: int) -> None:
        await self.collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"last_seen": datetime.now(timezone.utc)}}
        )

    async def set_super_admin(self, telegram_id: int, value: bool) -> bool:
        result = await self.collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"is_super_admin": value}}
        )
        return result.modified_count > 0

    async def delete_by_telegram_id(self, telegram_id: int) -> bool:
        result = await self.collection.delete_one({"telegram_id": int(telegram_id)})
        return result.deleted_count > 0
