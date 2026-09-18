"""Live Telegram message updates for broadcast job progress."""
from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest

from app.bot.keyboards.broadcast_menu import broadcast_control_keyboard


def format_broadcast_status_text(job: dict) -> str:
    job_id = str(job.get("_id", job.get("id", "")))
    status = job.get("status", "unknown")
    sent = int(job.get("sent_count") or 0)
    failed = int(job.get("failed_count") or 0)
    total = int(job.get("total_recipients") or 0)
    done = sent + failed
    pct = round((done / total) * 100, 1) if total else 0.0

    bar_filled = int(pct // 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    title = "🚀 Broadcast in progress"
    if status == "pending_approval":
        title = "⏳ Awaiting admin approval"
    elif status == "rejected":
        title = "❌ Broadcast rejected"
    elif status == "paused":
        title = "⏸ Broadcast paused"
    elif status == "completed":
        title = "✅ Broadcast completed"
    elif status == "cancelled":
        title = "❌ Broadcast cancelled"

    lines = [
        f"{title}\n",
        f"<b>Status:</b> {status}",
        f"<b>Progress:</b> {sent} sent · {failed} failed · {total} total",
        f"<code>{bar}</code> {pct}%",
        f"<b>Job:</b> <code>{job_id[:8]}…</code>",
    ]
    if failed and status in ("running", "paused", "cancelled", "completed"):
        lines.append(
            "\n<i>Most failures mean the user never /start this bot "
            "(Telegram blocks DMs) or blocked the bot.</i>"
        )
    return "\n".join(lines)


async def attach_status_message(broadcast_repo, job_id: str, chat_id: int, message_id: int) -> None:
    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {
            "status_chat_id": chat_id,
            "status_message_id": message_id,
            "owner_status_chat_id": chat_id,
            "owner_status_message_id": message_id,
            "status_message_final": False,
        }},
    )


async def _edit_status(bot, chat_id: int, message_id: int, text: str, markup) -> bool:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        return False


async def refresh_broadcast_status_message(bot, broadcast_repo, job_id: str) -> None:
    await refresh_broadcast_status_messages_for_job(bot, broadcast_repo, job_id)


async def refresh_broadcast_status_messages_for_job(bot, broadcast_repo, job_id: str) -> None:
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("status_message_final"):
        return

    status = job.get("status", "unknown")
    text = format_broadcast_status_text(job)
    markup = None
    if status in ("running", "paused"):
        markup = broadcast_control_keyboard(job_id, status)

    targets = []
    if job.get("owner_status_chat_id") and job.get("owner_status_message_id"):
        targets.append((job["owner_status_chat_id"], job["owner_status_message_id"]))
    elif job.get("status_chat_id") and job.get("status_message_id"):
        targets.append((job["status_chat_id"], job["status_message_id"]))
    if job.get("admin_status_chat_id") and job.get("admin_status_message_id"):
        pair = (job["admin_status_chat_id"], job["admin_status_message_id"])
        if pair not in targets:
            targets.append(pair)

    for chat_id, message_id in targets:
        await _edit_status(bot, chat_id, message_id, text, markup)

    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {"status_message_updated_at": datetime.now(timezone.utc)}},
    )

    if status in ("completed", "cancelled", "rejected"):
        await broadcast_repo.collection.update_one(
            {"_id": job_id},
            {"$set": {"status_message_final": True}},
        )


async def refresh_active_broadcast_status_messages(bot, broadcast_repo) -> None:
    cursor = broadcast_repo.collection.find({
        "status_message_id": {"$exists": True},
        "status_message_final": {"$ne": True},
        "status": {"$in": ["running", "paused", "completed", "cancelled"]},
    })
    jobs = await cursor.to_list(length=50)
    for job in jobs:
        await refresh_broadcast_status_message(bot, broadcast_repo, str(job["_id"]))
