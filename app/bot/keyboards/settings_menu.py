from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any


def settings_chat_picker_keyboard(chats: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in chats:
        title = c.get("title", "Chat")
        chat_id = c.get("chat_id")
        b.button(text=f"💬 {title}", callback_data=f"settings:hub:{chat_id}")
    b.button(text="← Menu", callback_data="menu:main")
    b.adjust(1, 1)
    return b.as_markup()


def approval_settings_keyboard(
    chat_id: int,
    auto_approval: bool,
    delay_seconds: int,
    captcha_enabled: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    toggle_text = "🟢 Auto Approval: ON" if auto_approval else "🔴 Auto Approval: OFF"
    builder.button(text=toggle_text, callback_data=f"approval:toggle:{chat_id}")

    captcha_text = "🛡 Captcha: ON ✅" if captcha_enabled else "🛡 Captcha: OFF"
    builder.button(text=captcha_text, callback_data=f"captcha:toggle:{chat_id}")

    delays = [
        ("⚡ Immediate", 0),
        ("⏱ 1m", 60),
        ("⏱ 5m", 300),
        ("⏱ 15m", 900),
        ("⏱ 30m", 1800),
        ("⏱ 1h", 3600),
        ("⏱ 2h", 7200),
    ]

    for label, seconds in delays:
        prefix = "✅ " if delay_seconds == seconds else ""
        builder.button(
            text=f"{prefix}{label}",
            callback_data=f"approval:delay:{chat_id}:{seconds}",
        )

    builder.button(text="✏️ Custom delay", callback_data=f"approval:delay:{chat_id}:custom")
    builder.button(text="← Back", callback_data=f"settings:hub:{chat_id}")
    builder.adjust(1, 1, 2, 2, 2, 1, 1)
    return builder.as_markup()
