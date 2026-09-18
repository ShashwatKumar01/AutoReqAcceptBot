"""Telegram /start deep-link payloads (e.g. Channel Help–style welcome unlock)."""

from __future__ import annotations

WELCOME_PREFIX = "wel_"


def welcome_start_payload(chat_id: int) -> str:
    return f"{WELCOME_PREFIX}{int(chat_id)}"


def welcome_deeplink(bot_username: str, chat_id: int) -> str:
    username = (bot_username or "").lstrip("@")
    return f"https://t.me/{username}?start={welcome_start_payload(chat_id)}"


def parse_welcome_start(args: str | None) -> int | None:
    if not args or not args.startswith(WELCOME_PREFIX):
        return None
    raw = args[len(WELCOME_PREFIX) :].strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
