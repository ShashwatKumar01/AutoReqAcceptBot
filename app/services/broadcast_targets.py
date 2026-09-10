"""Broadcast audience resolution (estimates + recipient user IDs)."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


TARGET_LABELS = {
    "all_users": "All users who /start the bot",
    "all_chat_members": "All members (every connected chat)",
    "all": "All members (scoped chats)",
    "chat_admins": "Chat admins who added the bot",
    "chat_members": "Members of a specific chat",
    "chat": "Specific chat ID (approved members)",
}


async def _scoped_chat_ids(chat_repo, chat_scope_owner_id: Optional[int]) -> list[int]:
    if chat_scope_owner_id:
        chats = await chat_repo.get_by_admin(int(chat_scope_owner_id))
        return [int(c["chat_id"]) for c in chats]
    cursor = chat_repo.collection.find({}, {"chat_id": 1})
    docs = await cursor.to_list(length=None)
    return [int(d["chat_id"]) for d in docs if d.get("chat_id") is not None]


async def estimate_recipients(
    target: str,
    *,
    chat_scope_owner_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    target_id: Optional[int] = None,
    user_repo=None,
    chat_repo=None,
    join_request_repo=None,
) -> int:
    scope = chat_scope_owner_id if chat_scope_owner_id is not None else owner_id
    ids = await collect_recipient_ids(
        target,
        chat_scope_owner_id=scope,
        target_id=target_id,
        user_repo=user_repo,
        chat_repo=chat_repo,
        join_request_repo=join_request_repo,
    )
    return len(ids)


async def collect_recipient_ids(
    target: str,
    *,
    chat_scope_owner_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    target_id: Optional[int] = None,
    user_repo=None,
    chat_repo=None,
    join_request_repo=None,
) -> list[int]:
    target = (target or "all_users").strip()
    scope = chat_scope_owner_id if chat_scope_owner_id is not None else owner_id

    if target in ("all_users", "master", "bot_users"):
        cursor = user_repo.collection.find({}, {"telegram_id": 1})
        docs = await cursor.to_list(length=None)
        return sorted({int(d["telegram_id"]) for d in docs if d.get("telegram_id")})

    if target in ("chat_admins", "admins"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        if not chat_ids:
            return []
        admins = await chat_repo.admins_collection.find(
            {"chat_id": {"$in": chat_ids}},
            {"user_id": 1},
        ).to_list(length=None)
        return sorted({int(a["user_id"]) for a in admins if a.get("user_id") is not None})

    if target in ("chat", "chat_members") and target_id:
        cid = int(target_id)
        cursor = join_request_repo.collection.find(
            {"chat_id": cid, "status": "approved"},
            {"user_id": 1},
        )
        docs = await cursor.to_list(length=None)
        ids = {int(d["user_id"]) for d in docs if d.get("user_id") is not None}
        user_docs = await user_repo.collection.find(
            {"chat_ids": cid},
            {"telegram_id": 1},
        ).to_list(length=None)
        ids.update(int(d["telegram_id"]) for d in user_docs if d.get("telegram_id") is not None)
        return sorted(ids)

    if target in ("all", "all_chat_members", "all_channels"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        if not chat_ids:
            return []
        cursor = join_request_repo.collection.find(
            {"chat_id": {"$in": chat_ids}, "status": "approved"},
            {"user_id": 1},
        )
        docs = await cursor.to_list(length=None)
        return sorted({int(d["user_id"]) for d in docs if d.get("user_id") is not None})

    return []
