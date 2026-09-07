from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def approval_settings_keyboard(
    chat_id: int,
    auto_approval: bool,
    delay_seconds: int,
    captcha_enabled: bool = False,
) -> InlineKeyboardMarkup:
    """Approval settings keyboard."""
    builder = InlineKeyboardBuilder()

    toggle_text = "🟢 Auto Approval: ON" if auto_approval else "🔴 Auto Approval: OFF"
    builder.button(text=toggle_text, callback_data=f"approval:toggle:{chat_id}")

    # Captcha mode toggle
    captcha_text = "🛡 Captcha: ON ✅" if captcha_enabled else "🛡 Captcha: OFF"
    builder.button(text=captcha_text, callback_data=f"captcha:toggle:{chat_id}")

    # Delay options
    delays = [
        ("⚡ Immediate", 0),
        ("⏱ 1m", 60),
        ("⏱ 5m", 300),
        ("⏱ 15m", 900),
        ("⏱ 30m", 1800),
        ("⏱ 1h", 3600),
        ("⏱ 2h", 7200)
    ]

    for text, val in delays:
        # Mark active delay
        btn_text = f"✅ {text}" if delay_seconds == val else text
        builder.button(text=btn_text, callback_data=f"approval:delay:{chat_id}:{val}")

    builder.button(text="✏️ Custom", callback_data=f"approval:delay:{chat_id}:custom")
    builder.button(text="← Back to Menu", callback_data="menu:main")

    # Row 1: two toggles (auto approval, captcha). Row 2+: 2 delay per row, 4 rows.
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()

def welcome_settings_keyboard(
    chat_id: int,
    has_text: bool = False,
    has_media: bool = False,
    has_buttons: bool = False,
) -> InlineKeyboardMarkup:
    """
    Welcome message editor keyboard.

    Per product decision, the legacy "welcome on/off + trigger + delay"
    controls are removed. The welcome message is always sent to newly
    approved members; admins only configure WHAT it looks like:
      - text  (with premium emoji / HTML formatting)
      - media (photo or video attached to the message)
      - buttons (inline keyboard)
      - preview before publishing
    """
    builder = InlineKeyboardBuilder()

    text_label = "✏️ Edit Text ✅" if has_text else "✏️ Edit Text"
    media_label = "🖼 Set Media ✅" if has_media else "🖼 Set Media"
    buttons_label = "🔘 Buttons ✅" if has_buttons else "🔘 Buttons"

    builder.button(text=text_label, callback_data=f"welcome:edit_text:{chat_id}")
    builder.button(text=media_label, callback_data=f"welcome:set_media:{chat_id}")
    builder.button(text=buttons_label, callback_data=f"welcome:edit_buttons:{chat_id}")
    builder.button(text="👁 Preview", callback_data=f"welcome:preview:{chat_id}")
    builder.button(text="🗑 Clear", callback_data=f"welcome:clear:{chat_id}")
    builder.button(text="← Back to Menu", callback_data="menu:main")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
