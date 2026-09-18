"""Deliver broadcast payloads to a user DM with HTML fallback."""

import re
from typing import Any

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def _parse_error(err: TelegramBadRequest) -> bool:
    m = str(err).lower()
    return any(
        x in m
        for x in ("parse", "entity", "can't find end", "wrong file", "caption is too long")
    )


async def send_broadcast_payload(bot, user_id: int, payload: dict) -> tuple[bool, str | None]:
    """
    Returns (success, error_reason).
    Retries without HTML if Telegram rejects entities.
    """
    msg_type = payload.get("type", "text")
    parse_mode = payload.get("parse_mode", "HTML")
    text = payload.get("text")
    caption = payload.get("caption")

    async def _send(use_html: bool) -> None:
        pm = parse_mode if use_html else None
        cap = caption if use_html else _strip_html(caption)
        body = text if use_html else _strip_html(text)
        if msg_type == "photo":
            await bot.send_photo(
                chat_id=user_id, photo=payload["photo"], caption=cap, parse_mode=pm,
            )
        elif msg_type == "video":
            await bot.send_video(
                chat_id=user_id, video=payload["video"], caption=cap, parse_mode=pm,
            )
        elif msg_type == "document":
            await bot.send_document(
                chat_id=user_id, document=payload["document"], caption=cap, parse_mode=pm,
            )
        elif msg_type == "animation":
            await bot.send_animation(
                chat_id=user_id, animation=payload["animation"], caption=cap, parse_mode=pm,
            )
        else:
            await bot.send_message(chat_id=user_id, text=body or "(empty)", parse_mode=pm)

    try:
        await _send(True)
        return True, None
    except TelegramForbiddenError:
        return False, "user_blocked_bot"
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "chat not found" in err:
            return False, "user_never_started_bot"
        if _parse_error(e):
            try:
                await _send(False)
                return True, None
            except TelegramForbiddenError:
                return False, "user_blocked_bot"
            except TelegramBadRequest as e2:
                return False, str(e2)[:200]
        return False, str(e)[:200]
    except Exception as e:
        return False, str(e)[:200]
