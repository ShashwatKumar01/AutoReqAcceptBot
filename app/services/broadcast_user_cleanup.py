"""Remove DB users who cannot receive bot DMs after a broadcast failure."""

from app.core.config import Settings

UNREACHABLE_BROADCAST_REASONS = frozenset({
    "user_blocked_bot",
    "user_never_started_bot",
})


async def remove_user_if_unreachable(
    user_repo,
    user_id: int,
    reason: str | None,
    settings: Settings,
) -> bool:
    if not user_repo or not reason or reason not in UNREACHABLE_BROADCAST_REASONS:
        return False
    if user_id in settings.super_admin_id_list:
        return False
    result = await user_repo.collection.delete_one({"telegram_id": int(user_id)})
    return result.deleted_count > 0
