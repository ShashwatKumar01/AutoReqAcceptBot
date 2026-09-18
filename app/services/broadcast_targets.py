"""Broadcast audience resolution (estimates + recipient user IDs). All sends are DM-only."""

from typing import Optional


TARGET_LABELS = {
    "all_users": "All bot users (/start)",
    "all_users_and_admins": "All bot users + chat admins (DM)",
    "all_chat_members": "All members (every connected chat)",
    "all": "All members (scoped chats)",
    "chat_admins": "Chat admins only (DM)",
    "chat_members": "All members of a chat (DM)",
    "chat_members_no_admins": "Chat members except admins (DM)",
    "specific_id": "Specific user or chat ID (DM)",
    "chat": "Specific chat ID (approved members)",
}


async def _scoped_chat_ids(chat_repo, chat_scope_owner_id: Optional[int]) -> list[int]:
    if chat_scope_owner_id:
        chats = await chat_repo.get_by_admin(int(chat_scope_owner_id))
        return [int(c["chat_id"]) for c in chats]
    cursor = chat_repo.collection.find(
        {"status": {"$ne": "disconnected"}},
        {"chat_id": 1},
    )
    docs = await cursor.to_list(length=None)
    return [int(d["chat_id"]) for d in docs if d.get("chat_id") is not None]


async def _admin_user_ids(chat_repo, chat_ids: list[int]) -> set[int]:
    if not chat_ids:
        return set()
    admins = await chat_repo.admins_collection.find(
        {"chat_id": {"$in": chat_ids}},
        {"user_id": 1},
    ).to_list(length=None)
    return {int(a["user_id"]) for a in admins if a.get("user_id") is not None}


async def _filter_can_dm(user_repo, ids: list[int]) -> list[int]:
    """Telegram only allows DM to users who have started the bot (stored in users)."""
    if not ids or not user_repo:
        return ids
    cursor = user_repo.collection.find(
        {"telegram_id": {"$in": ids}},
        {"telegram_id": 1},
    )
    docs = await cursor.to_list(length=None)
    allowed = {int(d["telegram_id"]) for d in docs if d.get("telegram_id") is not None}
    return sorted(i for i in ids if i in allowed)


async def _member_ids_for_chat(
    join_request_repo,
    user_repo,
    chat_id: int,
    *,
    exclude_admins: bool,
    chat_repo,
) -> list[int]:
    cid = int(chat_id)
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
    if exclude_admins:
        admin_ids = await _admin_user_ids(chat_repo, [cid])
        ids -= admin_ids
    return sorted(ids)


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

    if target == "all_users_and_admins":
        cursor = user_repo.collection.find({}, {"telegram_id": 1})
        docs = await cursor.to_list(length=None)
        ids = {int(d["telegram_id"]) for d in docs if d.get("telegram_id")}
        chat_ids = await _scoped_chat_ids(chat_repo, None)
        ids.update(await _admin_user_ids(chat_repo, chat_ids))
        return sorted(ids)

    if target in ("chat_admins", "admins"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        return sorted(await _admin_user_ids(chat_repo, chat_ids))

    if target == "chat_members_no_admins" and target_id:
        raw = await _member_ids_for_chat(
            join_request_repo, user_repo, int(target_id),
            exclude_admins=True, chat_repo=chat_repo,
        )
        return await _filter_can_dm(user_repo, raw)

    if target in ("chat", "chat_members") and target_id:
        raw = await _member_ids_for_chat(
            join_request_repo, user_repo, int(target_id),
            exclude_admins=False, chat_repo=chat_repo,
        )
        return await _filter_can_dm(user_repo, raw)

    if target == "specific_id" and target_id is not None:
        tid = int(target_id)
        if tid > 0:
            return await _filter_can_dm(user_repo, [tid])
        raw = await _member_ids_for_chat(
            join_request_repo, user_repo, tid,
            exclude_admins=True, chat_repo=chat_repo,
        )
        return await _filter_can_dm(user_repo, raw)

    if target in ("all", "all_chat_members", "all_channels"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        if not chat_ids:
            return []
        cursor = join_request_repo.collection.find(
            {"chat_id": {"$in": chat_ids}, "status": "approved"},
            {"user_id": 1},
        )
        docs = await cursor.to_list(length=None)
        raw = sorted({int(d["user_id"]) for d in docs if d.get("user_id") is not None})
        return await _filter_can_dm(user_repo, raw)

    return []
