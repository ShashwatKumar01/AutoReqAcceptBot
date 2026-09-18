"""Broadcast audience resolution (estimates + recipient user IDs). All sends are DM-only."""

from typing import Optional


TARGET_LABELS = {
    "all_users": "All bot users (/start)",
    "all_users_and_admins": "All bot users + chat admins (DM)",
    "all_chat_members": "All members (every connected chat)",
    "all": "All members (scoped chats)",
    "chat_admins": "Chat admins only (DM)",
    "chat_members": "Members of a chat (DM)",
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


async def _dm_reachable_user_ids(user_repo, ids: list[int] | None = None) -> list[int]:
    """
    Users who opened a private chat with the bot (/start in DM).
    Join-request approval alone does NOT make someone reachable.
    """
    if not user_repo:
        return []
    query = {"private_chat_started": True}
    if ids is not None:
        if not ids:
            return []
        query["telegram_id"] = {"$in": ids}
    cursor = user_repo.collection.find(query, {"telegram_id": 1})
    docs = await cursor.to_list(length=None)
    return sorted({int(d["telegram_id"]) for d in docs if d.get("telegram_id") is not None})


async def _member_ids_for_chat(
    join_request_repo,
    user_repo,
    chat_id: int,
    *,
    exclude_admins: bool,
    chat_repo,
) -> list[int]:
    cid = int(chat_id)
    cursor = user_repo.collection.find(
        {"chat_ids": cid, "private_chat_started": True},
        {"telegram_id": 1},
    )
    docs = await cursor.to_list(length=None)
    ids = {int(d["telegram_id"]) for d in docs if d.get("telegram_id") is not None}
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
    summary = await audience_summary(
        target,
        chat_scope_owner_id=chat_scope_owner_id,
        owner_id=owner_id,
        target_id=target_id,
        user_repo=user_repo,
        chat_repo=chat_repo,
        join_request_repo=join_request_repo,
    )
    return summary["eligible"]


async def audience_summary(
    target: str,
    *,
    chat_scope_owner_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    target_id: Optional[int] = None,
    user_repo=None,
    chat_repo=None,
    join_request_repo=None,
) -> dict[str, int]:
    """eligible = DM-reachable for this target; tracked = stored members in scope (if applicable)."""
    scope = chat_scope_owner_id if chat_scope_owner_id is not None else owner_id
    eligible = len(
        await collect_recipient_ids(
            target,
            chat_scope_owner_id=scope,
            target_id=target_id,
            user_repo=user_repo,
            chat_repo=chat_repo,
            join_request_repo=join_request_repo,
        )
    )
    tracked = await _tracked_audience_size(
        target,
        chat_scope_owner_id=scope,
        target_id=target_id,
        user_repo=user_repo,
        chat_repo=chat_repo,
    )
    return {"eligible": eligible, "tracked": tracked}


async def _tracked_audience_size(
    target: str,
    *,
    chat_scope_owner_id: Optional[int] = None,
    target_id: Optional[int] = None,
    user_repo=None,
    chat_repo=None,
) -> int:
    if not user_repo:
        return 0
    target = (target or "all_users").strip()

    if target in ("all_users", "master", "bot_users"):
        return await user_repo.count_total()

    if target == "all_users_and_admins":
        return await user_repo.count_total()

    if target in ("chat_admins", "admins"):
        chat_ids = await _scoped_chat_ids(chat_repo, chat_scope_owner_id)
        return len(await _admin_user_ids(chat_repo, chat_ids))

    if target in ("chat_members_no_admins", "chat", "chat_members") and target_id:
        return await user_repo.count_tracked_in_chats([int(target_id)])

    if target == "specific_id" and target_id is not None:
        tid = int(target_id)
        if tid > 0:
            return 1
        return await user_repo.count_tracked_in_chats([tid])

    if target in ("all", "all_chat_members", "all_channels"):
        chat_ids = await _scoped_chat_ids(chat_repo, chat_scope_owner_id)
        return await user_repo.count_tracked_in_chats(chat_ids)

    return 0


def format_audience_lines(summary: dict[str, int]) -> str:
    eligible = int(summary.get("eligible") or 0)
    tracked = int(summary.get("tracked") or 0)
    lines = [f"Broadcast eligible: <b>{eligible}</b>"]
    if tracked > eligible:
        lines.append(
            f"Tracked in bot DB: <b>{tracked}</b> "
            f"(<i>{tracked - eligible} have not /start the bot in DM yet</i>)"
        )
    return "\n".join(lines)


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
        return await _dm_reachable_user_ids(user_repo)

    if target == "all_users_and_admins":
        ids = set(await _dm_reachable_user_ids(user_repo))
        chat_ids = await _scoped_chat_ids(chat_repo, None)
        ids.update(await _admin_user_ids(chat_repo, chat_ids))
        return sorted(ids)

    if target in ("chat_admins", "admins"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        return sorted(await _admin_user_ids(chat_repo, chat_ids))

    if target == "chat_members_no_admins" and target_id:
        return await _member_ids_for_chat(
            join_request_repo, user_repo, int(target_id),
            exclude_admins=True, chat_repo=chat_repo,
        )

    if target in ("chat", "chat_members") and target_id:
        return await _member_ids_for_chat(
            join_request_repo, user_repo, int(target_id),
            exclude_admins=False, chat_repo=chat_repo,
        )

    if target == "specific_id" and target_id is not None:
        tid = int(target_id)
        if tid > 0:
            return await _dm_reachable_user_ids(user_repo, [tid])
        return await _member_ids_for_chat(
            join_request_repo, user_repo, tid,
            exclude_admins=True, chat_repo=chat_repo,
        )

    if target in ("all", "all_chat_members", "all_channels"):
        chat_ids = await _scoped_chat_ids(chat_repo, scope)
        if not chat_ids:
            return []
        cursor = user_repo.collection.find(
            {
                "chat_ids": {"$in": chat_ids},
                "private_chat_started": True,
            },
            {"telegram_id": 1},
        )
        docs = await cursor.to_list(length=None)
        return sorted({int(d["telegram_id"]) for d in docs if d.get("telegram_id") is not None})

    return []
