from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

class ChatRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db['chats']
        self.admins_collection = db['chat_admins']
        self.settings_collection = db['chat_settings']

    async def upsert_chat(self, chat_data: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = chat_data['chat_id']
        now = datetime.now(timezone.utc)

        update_doc = {
            "$set": {k: v for k, v in chat_data.items() if k != 'chat_id'},
            "$setOnInsert": {"created_at": now, "total_join_requests": 0, "total_approved": 0, "total_welcome_sent": 0}
        }

        return await self.collection.find_one_and_update(
            {"chat_id": chat_id},
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    # Aliases matching what handlers/services call
    async def upsert(self, chat_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.upsert_chat(chat_data)

    async def get(self, chat_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_by_chat_id(chat_id)

    async def get_by_admin(self, user_id: int) -> List[Dict[str, Any]]:
        return await self.get_chats_by_connected_user(user_id)

    async def count(self) -> int:
        return await self.count_total()

    async def update_settings(self, chat_id: int, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.upsert_settings(chat_id, settings_data)

    async def get_chat_settings(self, chat_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_settings(chat_id)

    async def get_chat_settings_with_defaults(self, chat_id: int) -> Dict[str, Any]:
        return await self.get_settings_with_defaults(chat_id)

    async def get_by_chat_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"chat_id": chat_id})

    async def get_chats_by_connected_user(self, user_id: int) -> List[Dict[str, Any]]:
        admin_records = await self.admins_collection.find({"user_id": user_id}).to_list(length=None)
        chat_ids = [record['chat_id'] for record in admin_records]
        if not chat_ids:
            return []
        return await self.collection.find({"chat_id": {"$in": chat_ids}}).to_list(length=None)

    async def get_all_active(self) -> List[Dict[str, Any]]:
        return await self.collection.find({"status": "active"}).to_list(length=None)

    async def update_status(self, chat_id: int, status: str) -> bool:
        result = await self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def update_permissions(self, chat_id: int, permissions: Dict[str, Any], has_permission: bool) -> bool:
        result = await self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"permissions": permissions, "has_permission": has_permission, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def increment_counter(self, chat_id: int, field: str, amount: int = 1) -> None:
        await self.collection.update_one(
            {"chat_id": chat_id},
            {"$inc": {field: amount}}
        )

    async def count_total(self) -> int:
        return await self.collection.count_documents({})

    async def count_by_type(self, chat_type: str) -> int:
        return await self.collection.count_documents({"chat_type": chat_type})

    async def count_by_status(self, status: str) -> int:
        return await self.collection.count_documents({"status": status})

    # --- Admin management ---
    async def upsert_admin(self, chat_id: int, user_id: int) -> None:
        await self.admins_collection.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True
        )

    async def remove_admin(self, chat_id: int, user_id: int) -> None:
        await self.admins_collection.delete_one({"chat_id": chat_id, "user_id": user_id})

    async def get_admins(self, chat_id: int) -> List[Dict[str, Any]]:
        return await self.admins_collection.find({"chat_id": chat_id}).to_list(length=None)

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        record = await self.admins_collection.find_one({"chat_id": chat_id, "user_id": user_id})
        return record is not None

    # --- Settings ---
    async def get_settings(self, chat_id: int) -> Optional[Dict[str, Any]]:
        return await self.settings_collection.find_one({"chat_id": chat_id})

    async def upsert_settings(self, chat_id: int, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        update_doc = {
            "$set": {k: v for k, v in settings_data.items() if k != 'chat_id'},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)}
        }
        return await self.settings_collection.find_one_and_update(
            {"chat_id": chat_id},
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    async def update_settings_field(self, chat_id: int, field: str, value: Any) -> bool:
        result = await self.settings_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {field: value, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def get_settings_with_defaults(self, chat_id: int) -> Dict[str, Any]:
        settings = await self.get_settings(chat_id)
        defaults = {
            "chat_id": chat_id,
            "auto_approval_enabled": True,
            "approval_delay_seconds": 0,
            "auto_approval_delay": 0,
            "captcha_enabled": False,
            # Welcome
            "welcome_enabled": True,
            "welcome_trigger": "on_approval",
            "welcome_delay_seconds": 0,
            "welcome_text": "",
            "welcome_media_file_id": "",
            "welcome_media_type": "",
            "welcome_buttons": [],
            "welcome_parse_mode": "HTML",
            # Goodbye
            "goodbye_enabled": False,
            "goodbye_text": "",
            "goodbye_media_file_id": "",
            "goodbye_media_type": "",
            "goodbye_buttons": [],
        }
        if settings:
            return {**defaults, **settings}
        return defaults

    def parse_approval_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize approval settings from chat_settings document."""
        nested = settings.get("approval_settings") or {}
        enabled = settings.get(
            "auto_approval_enabled",
            nested.get("enabled", True),
        )
        delay = settings.get(
            "approval_delay_seconds",
            settings.get(
                "auto_approval_delay",
                nested.get("delay", 0),
            ),
        )
        return {
            "enabled": bool(enabled),
            "delay": int(delay or 0),
            "captcha_enabled": bool(settings.get("captcha_enabled", False)),
        }

    async def get_approval_settings(self, chat_id: int) -> Dict[str, Any]:
        settings = await self.get_settings_with_defaults(chat_id)
        return self.parse_approval_settings(settings)

    async def save_approval_settings(
        self,
        chat_id: int,
        *,
        enabled: bool | None = None,
        delay: int | None = None,
        captcha_enabled: bool | None = None,
    ) -> Dict[str, Any]:
        """Persist approval settings in both flat and nested formats."""
        current = await self.get_approval_settings(chat_id)
        if enabled is not None:
            current["enabled"] = enabled
        if delay is not None:
            current["delay"] = delay
        if captcha_enabled is not None:
            current["captcha_enabled"] = captcha_enabled

        await self.upsert_settings(chat_id, {
            "auto_approval_enabled": current["enabled"],
            "approval_delay_seconds": current["delay"],
            "auto_approval_delay": current["delay"],
            "approval_settings": {
                "enabled": current["enabled"],
                "delay": current["delay"],
            },
            "captcha_enabled": current["captcha_enabled"],
        })
        return current
