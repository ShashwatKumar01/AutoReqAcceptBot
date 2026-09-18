"""Chat-owner broadcast moderation: super admin approve / reject before send."""

from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.core.config import Settings
from app.services.broadcast_admin_notify import notify_super_admins
from app.services.broadcast_status_message import (
    attach_status_message,
    format_broadcast_status_text,
    refresh_broadcast_status_messages_for_job,
    _edit_status,
)
from app.services.broadcast_targets import TARGET_LABELS


def approval_contact(settings: Settings) -> str:
    return (getattr(settings, "broadcast_approval_contact", None) or "@woxic_01").strip()


def payload_preview(payload: dict, max_len: int = 400) -> str:
    if not payload:
        return "(empty)"
    kind = payload.get("type", "text")
    if kind == "text":
        body = payload.get("text") or ""
    else:
        body = payload.get("caption") or f"[{kind} attachment]"
    body = body.replace("<", "&lt;").replace(">", "&gt;")
    if len(body) > max_len:
        return body[: max_len - 1] + "…"
    return body or f"({kind})"


def format_owner_submitted(settings: Settings, job: dict) -> str:
    contact = approval_contact(settings)
    job_id = str(job.get("_id", ""))[:8]
    return (
        "📨 <b>Broadcast submitted for approval</b>\n\n"
        "Your message was sent to the platform admin for review.\n"
        f"You will be notified when it is approved or rejected.\n\n"
        f"Questions: {contact}\n"
        f"<b>Ref:</b> <code>{job_id}…</code>"
    )


def format_admin_review_request(
    job: dict,
    owner_id: int,
    owner_name: str,
    chat_title: str | None,
) -> str:
    target = job.get("target", "")
    label = TARGET_LABELS.get(target, target)
    tid = job.get("target_id")
    if tid:
        label = f"{label} ({tid})"
    total = int(job.get("total_recipients") or 0)
    preview = payload_preview(job.get("payload") or {})
    chat_line = f"<b>Chat:</b> {chat_title}\n" if chat_title else ""
    return (
        "🛡 <b>Broadcast approval needed</b>\n\n"
        f"<b>From:</b> {owner_name} (<code>{owner_id}</code>)\n"
        f"{chat_line}"
        f"<b>Audience:</b> {label}\n"
        f"<b>Broadcast eligible:</b> {total}\n\n"
        f"<b>Content preview:</b>\n{preview}\n\n"
        "Approve to start sending in DM, or reject with a remark."
    )


def format_owner_rejected(settings: Settings, job: dict, remark: str) -> str:
    contact = approval_contact(settings)
    return (
        "❌ <b>Broadcast rejected</b>\n\n"
        f"<b>Admin remark:</b>\n{remark}\n\n"
        f"Questions: {contact}"
    )


def format_owner_approved(job: dict, remark: str | None) -> str:
    lines = ["✅ <b>Broadcast approved</b> — sending now…\n"]
    if remark:
        lines.append(f"<b>Admin note:</b>\n{remark}\n")
    lines.append(format_broadcast_status_text(job))
    return "\n".join(lines)


async def _clear_admin_approval_keyboard(bot: Bot, broadcast_repo, job_id: str) -> None:
    job = await broadcast_repo.get_job(job_id)
    if not job:
        return
    cid = job.get("admin_status_chat_id")
    mid = job.get("admin_status_message_id")
    if cid and mid:
        try:
            await bot.edit_message_reply_markup(chat_id=cid, message_id=mid, reply_markup=None)
        except Exception:
            pass


async def notify_owner(bot: Bot, owner_id: int, text: str) -> None:
    try:
        await bot.send_message(owner_id, text, parse_mode="HTML")
    except Exception:
        pass


async def submit_pending_approval(
    bot: Bot,
    settings: Settings,
    broadcast_repo,
    job: dict,
    owner_chat_id: int,
    owner_message_id: int,
    owner_display: str,
    chat_title: str | None,
    approval_keyboard: InlineKeyboardMarkup,
) -> None:
    job_id = str(job["_id"])
    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {
            "owner_status_chat_id": owner_chat_id,
            "owner_status_message_id": owner_message_id,
            "requires_approval": True,
            "approval_status": "pending",
        }},
    )
    await attach_status_message(broadcast_repo, job_id, owner_chat_id, owner_message_id)

    text = format_admin_review_request(
        job, job["owner_id"], owner_display, chat_title,
    )
    for admin_id in settings.super_admin_id_list:
        try:
            msg = await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
                reply_markup=approval_keyboard,
            )
            watch = {
                "admin_id": admin_id,
                "chat_id": admin_id,
                "message_id": msg.message_id,
            }
            job = await broadcast_repo.get_job(job_id) or {}
            watches = list(job.get("admin_status_watches") or [])
            watches.append(watch)
            await broadcast_repo.collection.update_one(
                {"_id": job_id},
                {"$set": {
                    f"approval_msg_{admin_id}": msg.message_id,
                    "admin_status_chat_id": admin_id,
                    "admin_status_message_id": msg.message_id,
                    "admin_status_watches": watches,
                }},
            )
        except Exception:
            pass


async def approve_broadcast(
    bot: Bot,
    settings: Settings,
    broadcast_repo,
    job_id: str,
    reviewer_id: int,
    remark: str | None,
) -> dict | None:
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("approval_status") != "pending":
        return None

    now = datetime.now(timezone.utc)
    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {
            "status": "running",
            "approval_status": "approved",
            "approval_remark": remark or "",
            "reviewed_by": reviewer_id,
            "reviewed_at": now,
        }},
    )
    job = await broadcast_repo.get_job(job_id)
    await _clear_admin_approval_keyboard(bot, broadcast_repo, job_id)
    await refresh_broadcast_status_messages_for_job(
        bot, broadcast_repo, job_id, settings=settings,
    )
    owner_id = job.get("owner_id")
    if owner_id and remark:
        await notify_owner(bot, owner_id, f"✅ <b>Broadcast approved</b>\n\n{remark}")
    return job


async def reject_broadcast(
    bot: Bot,
    settings: Settings,
    broadcast_repo,
    job_id: str,
    reviewer_id: int,
    remark: str,
) -> dict | None:
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("approval_status") != "pending":
        return None

    now = datetime.now(timezone.utc)
    await broadcast_repo.collection.update_one(
        {"_id": job_id},
        {"$set": {
            "status": "rejected",
            "approval_status": "rejected",
            "approval_remark": remark,
            "reviewed_by": reviewer_id,
            "reviewed_at": now,
            "status_message_final": True,
        }},
    )
    job = await broadcast_repo.get_job(job_id)
    owner_id = job.get("owner_id")
    reject_text = format_owner_rejected(settings, job, remark)
    oc, om = job.get("owner_status_chat_id"), job.get("owner_status_message_id")
    if oc and om:
        await _edit_status(bot, oc, om, reject_text, None)
    elif owner_id:
        await notify_owner(bot, owner_id, reject_text)

    await _clear_admin_approval_keyboard(bot, broadcast_repo, job_id)

    admin_text = (
        f"⛔ <b>Broadcast rejected</b>\n\n"
        f"<b>Remark:</b> {remark}\n"
        f"<b>Job:</b> <code>{job_id[:8]}…</code>"
    )
    await notify_super_admins(bot, settings, admin_text)
    return job
