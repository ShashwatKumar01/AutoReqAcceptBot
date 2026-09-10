"""DM super admins when broadcasts start and finish."""

from aiogram import Bot

from app.core.config import Settings


def _target_label(job: dict) -> str:
    target = job.get("target") or "?"
    tid = job.get("target_id")
    labels = {
        "all_users": "All users who /start the bot",
        "master": "All users who /start the bot",
        "bot_users": "All users who /start the bot",
        "all": "All members (your channels/groups)",
        "all_chat_members": "All members (your channels/groups)",
        "all_channels": "All members (your channels/groups)",
        "chat_admins": "Chat admins who linked the bot",
        "admins": "Chat admins who linked the bot",
        "chat": f"Specific chat <code>{tid}</code>",
        "chat_members": f"Specific chat <code>{tid}</code>",
    }
    return labels.get(target, target)


def format_broadcast_started(job: dict, starter_id: int | None) -> str:
    job_id = str(job.get("_id", job.get("id", "")))
    total = int(job.get("total_recipients") or 0)
    who = f"<code>{starter_id}</code>" if starter_id else "—"
    return (
        "📢 <b>Broadcast started</b>\n\n"
        f"<b>Target:</b> {_target_label(job)}\n"
        f"<b>Recipients (est.):</b> {total}\n"
        f"<b>Started by:</b> {who}\n"
        f"<b>Job:</b> <code>{job_id[:8]}…</code>"
    )


def format_broadcast_finished(job: dict) -> str:
    job_id = str(job.get("_id", job.get("id", "")))
    status = job.get("status", "unknown")
    sent = int(job.get("sent_count") or 0)
    failed = int(job.get("failed_count") or 0)
    total = int(job.get("total_recipients") or 0)
    title = "✅ Broadcast finished"
    if status == "cancelled":
        title = "⛔ Broadcast cancelled"
    return (
        f"{title}\n\n"
        f"<b>Target:</b> {_target_label(job)}\n"
        f"<b>Sent:</b> {sent} · <b>Failed:</b> {failed} · <b>Total:</b> {total}\n"
        f"<b>Job:</b> <code>{job_id[:8]}…</code>"
    )


async def notify_super_admins(
    bot: Bot,
    settings: Settings,
    text: str,
) -> None:
    for admin_id in settings.super_admin_id_list:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def notify_broadcast_started(
    bot: Bot,
    settings: Settings,
    job: dict,
    starter_id: int | None,
) -> None:
    await notify_super_admins(bot, settings, format_broadcast_started(job, starter_id))


async def notify_broadcast_finished(bot: Bot, settings: Settings, job: dict) -> None:
    if job.get("status") not in ("completed", "cancelled"):
        return
    await notify_super_admins(bot, settings, format_broadcast_finished(job))


async def notify_broadcast_finished_if_needed(
    bot: Bot,
    settings: Settings,
    broadcast_repo,
    job_id: str,
) -> None:
    """Send finish DM once per job (completed or cancelled)."""
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("admin_finish_notified"):
        return
    if job.get("status") not in ("completed", "cancelled"):
        return
    await notify_broadcast_finished(bot, settings, job)
    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {"admin_finish_notified": True}},
    )
