"""Keep all super admins in sync on broadcast progress (pause / cancel / %)."""

from app.core.config import Settings
from app.services.broadcast_status_message import (
    format_broadcast_status_text,
    _edit_status,
)
from app.bot.keyboards.broadcast_menu import broadcast_control_keyboard


def _merge_watches(job: dict) -> list[dict]:
    watches: list[dict] = list(job.get("admin_status_watches") or [])
    seen = {(w.get("chat_id"), w.get("message_id")) for w in watches if w.get("message_id")}

    legacy_cid = job.get("admin_status_chat_id")
    legacy_mid = job.get("admin_status_message_id")
    if legacy_cid and legacy_mid and (legacy_cid, legacy_mid) not in seen:
        watches.append({
            "admin_id": legacy_cid,
            "chat_id": legacy_cid,
            "message_id": legacy_mid,
        })
    return watches


async def ensure_super_admin_watch_messages(
    bot,
    settings: Settings,
    broadcast_repo,
    job_id: str,
) -> None:
    """Create or update a progress message for every super admin."""
    job = await broadcast_repo.get_job(job_id)
    if not job:
        return

    status = job.get("status", "")
    if status not in ("running", "paused", "completed", "cancelled", "pending_approval"):
        return

    text = format_broadcast_status_text(job)
    markup = None
    if status in ("running", "paused"):
        markup = broadcast_control_keyboard(job_id, status)

    watches = _merge_watches(job)
    known_admins = {w.get("admin_id") for w in watches}

    for admin_id in settings.super_admin_id_list:
        if admin_id in known_admins:
            continue
        try:
            msg = await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=markup)
            watches.append({
                "admin_id": admin_id,
                "chat_id": admin_id,
                "message_id": msg.message_id,
            })
        except Exception:
            pass

    for w in watches:
        cid, mid = w.get("chat_id"), w.get("message_id")
        if cid and mid:
            await _edit_status(bot, cid, mid, text, markup)

    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {
            "admin_status_watches": watches,
            "admin_status_chat_id": watches[0]["chat_id"] if watches else job.get("admin_status_chat_id"),
            "admin_status_message_id": watches[0]["message_id"] if watches else job.get("admin_status_message_id"),
        }},
    )
