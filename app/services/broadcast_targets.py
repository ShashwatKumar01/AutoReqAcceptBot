"""Broadcast audience resolution (estimates + recipient user IDs)."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


async def _owner_chat_ids(chat_repo, owner_id: Optional[int]) -> list[int]:
    if owner_id:
        chats = await chat_repo.get_by_admin(int(owner_id))
        return [int(c["chat_id"]) for c in chats]
    cursor = chat_repo.collection.find({}, {"chat_id": 1})
    docs = await cursor.to_list(length=None)
    return [int(d["chat_id"]) for d in docs if d.get("chat_id") is not None]


async def estimate_recipients(
    target: str,
    *,
    owner_id: Optional[int],
    target_id: Optional[int],
    user_repo,
    chat_repo,
    join_request_repo,
) -> int:
    ids = await collect_recipient_ids(
        target,
        owner_id=owner_id,
        target_id=target_id,
        user_repo=user_repo,
        chat_repo=chat_repo,
        join_request_repo=join_request_repo,
    )
    return len(ids)


async def collect_recipient_ids(
    target: str,
    *,
    owner_id: Optional[int],
    target_id: Optional[int],
    user_repo,
    chat_repo,
    join_request_repo,
) -> list[int]:
    target = (target or "all_users").strip()

    if target in ("all_users", "master", "bot_users"):
        cursor = user_repo.collection.find({}, {"telegram_id": 1})
        docs = await cursor.to_list(length=None)
        return sorted({int(d["telegram_id"]) for d in docs if d.get("telegram_id")})

    if target in ("chat_admins", "admins"):
        chat_ids = await _owner_chat_ids(chat_repo, owner_id)
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
        return sorted({int(d["user_id"]) for d in docs if d.get("user_id") is not None})

    if target in ("all", "all_chat_members", "all_channels"):
        chat_ids = await _owner_chat_ids(chat_repo, owner_id)
        if not chat_ids:
            return []
        cursor = join_request_repo.collection.find(
            {"chat_id": {"$in": chat_ids}, "status": "approved"},
            {"user_id": 1},
        )
        docs = await cursor.to_list(length=None)
        return sorted({int(d["user_id"]) for d in docs if d.get("user_id") is not None})

    return []
