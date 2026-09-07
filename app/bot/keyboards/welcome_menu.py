from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any


def _trigger_label(trigger: str, delay: int) -> str:
    if trigger == "on_request":
        return "On Request"
    if delay == 300:
        return "5m after"
    if delay == 600:
        return "10m after"
    if delay == 1800:
        return "30m after"
    if delay > 0:
        return f"{delay // 60}m after"
    return "On Approval"


def welcome_editor_keyboard(
    chat_id: int,
    enabled: bool,
    has_text: bool,
    has_media: bool,
    btn_count: int,
    trigger: str,
    delay: int,
) -> InlineKeyboardMarkup:
    """Main welcome editor keyboard."""
    b = InlineKeyboardBuilder()

    toggle_icon = "✅" if enabled else "❌"
    b.button(text=f"{toggle_icon} Welcome {'ON' if enabled else 'OFF'}", callback_data=f"welcome:toggle:{chat_id}")

    text_icon = "✅ " if has_text else ""
    b.button(text=f"📝 {text_icon}{'Edit' if has_text else 'Add'} Message", callback_data=f"welcome:edit_text:{chat_id}")

    media_icon = "✅ " if has_media else ""
    b.button(text=f"🖼 {media_icon}{'Change' if has_media else 'Add'} Photo/Video", callback_data=f"welcome:set_media:{chat_id}")

    if has_media:
        b.button(text="🗑 Remove Media", callback_data=f"welcome:remove_media:{chat_id}")

    b.button(text=f"🔘 Buttons ({btn_count})", callback_data=f"welcome:buttons:{chat_id}")

    trigger_label = _trigger_label(trigger, delay)
    b.button(text=f"⏰ Timing: {trigger_label}", callback_data=f"welcome:timing:{chat_id}")

    b.button(text="👁 Preview", callback_data=f"welcome:preview:{chat_id}")
    b.button(text="← Back to Menu", callback_data="menu:main")

    b.adjust(1)
    return b.as_markup()


def welcome_timing_keyboard(
    chat_id: int,
    current_trigger: str,
    current_delay: int,
) -> InlineKeyboardMarkup:
    """Timing/trigger picker keyboard."""
    b = InlineKeyboardBuilder()

    options = [
        ("📩 On Request (before approval)", "on_request", 0),
        ("✅ On Approval (immediately)", "on_approval", 0),
        ("⏱ 5 min after approval", "delayed", 300),
        ("⏱ 10 min after approval", "delayed", 600),
        ("⏱ 30 min after approval", "delayed", 1800),
    ]

    for label, trigger, delay in options:
        if trigger == "on_request":
            is_selected = current_trigger == "on_request"
            cb = f"welcome:trigger:{chat_id}:on_request"
        elif trigger == "on_approval":
            is_selected = current_trigger in ("on_approval", "") and current_delay == 0
            cb = f"welcome:trigger:{chat_id}:on_approval"
        else:
            is_selected = current_trigger == "delayed" and current_delay == delay
            cb = f"welcome:trigger:{chat_id}:delay:{delay}"

        prefix = "✅ " if is_selected else ""
        b.button(text=f"{prefix}{label}", callback_data=cb)

    # Check if custom delay selected (not one of the presets)
    presets = {0, 300, 600, 1800}
    is_custom = current_trigger == "delayed" and current_delay not in presets
    custom_prefix = "✅ " if is_custom else ""
    b.button(text=f"{custom_prefix}✏️ Custom delay", callback_data=f"welcome:trigger:{chat_id}:custom")
    b.button(text="← Back", callback_data=f"welcome:edit:{chat_id}")

    b.adjust(1)
    return b.as_markup()


def welcome_buttons_keyboard(
    chat_id: int,
    buttons: List[Dict[str, Any]],
) -> InlineKeyboardMarkup:
    """Button manager keyboard."""
    b = InlineKeyboardBuilder()

    for i, btn in enumerate(buttons):
        label = btn.get("text", f"Button {i+1}")[:20]
        if btn.get("url"):
            target = btn["url"][:25]
        elif btn.get("callback_data"):
            target = "popup:" + btn["callback_data"][7:][:18]
        else:
            target = "(no target)"
        b.button(
            text=f"🗑 [{i+1}] {label} → {target}",
            callback_data=f"welcome:btn_remove:{chat_id}:{i}",
        )

    if len(buttons) < 10:
        b.button(text="➕ Add Button", callback_data=f"welcome:btn_add:{chat_id}")

    b.button(text="← Back", callback_data=f"welcome:edit:{chat_id}")
    b.adjust(1)
    return b.as_markup()


def welcome_chat_picker_keyboard(chats: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Chat picker for welcome config."""
    b = InlineKeyboardBuilder()
    for c in chats:
        title = c.get("title", "Chat")
        chat_id = c.get("chat_id")
        b.button(text=f"💬 {title}", callback_data=f"welcome:pick:{chat_id}")
    b.button(text="← Back", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()

