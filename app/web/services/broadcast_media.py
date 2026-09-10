"""Resolve web-uploaded broadcast media to Telegram file_id payloads."""

from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.core.utils import build_broadcast_payload


async def upload_broadcast_media(
    bot: Bot,
    admin_telegram_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str | None = None,
) -> dict:
    """Upload bytes via bot to super-admin DM; return broadcast payload with file_id."""
    if not file_bytes:
        raise ValueError("empty file")

    name = filename or "upload"
    lower = name.lower()
    inp = BufferedInputFile(file_bytes, filename=name)

    cap_kw = {"caption": caption, "parse_mode": "HTML"} if caption else {}
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        msg = await bot.send_photo(chat_id=admin_telegram_id, photo=inp, **cap_kw)
        payload = build_broadcast_payload(msg)
    elif lower.endswith((".mp4", ".mov", ".mkv")):
        msg = await bot.send_video(chat_id=admin_telegram_id, video=inp, **cap_kw)
        payload = build_broadcast_payload(msg)
    elif lower.endswith(".gif"):
        msg = await bot.send_animation(chat_id=admin_telegram_id, animation=inp, **cap_kw)
        payload = build_broadcast_payload(msg)
    else:
        msg = await bot.send_document(chat_id=admin_telegram_id, document=inp, **cap_kw)
        payload = build_broadcast_payload(msg)

    if not payload:
        raise ValueError("unsupported media type")
    try:
        await bot.delete_message(chat_id=admin_telegram_id, message_id=msg.message_id)
    except Exception:
        pass
    return payload
