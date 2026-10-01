from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.styled import STYLE_PRIMARY

def main_menu_keyboard(is_super_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu shown after /start."""
    builder = InlineKeyboardBuilder()

    # Row 1 — pick a chat first for settings; feature shortcuts still ask for chat when needed
    builder.button(text="💬 Manage a chat", callback_data="menu:settings")
    builder.button(text="👋 Welcome", callback_data="menu:welcome")
    # Row 2
    builder.button(text="🚪 Goodbye", callback_data="menu:goodbye")
    builder.button(text="📢 Broadcast", callback_data="menu:broadcast")
    # Row 3 — tutorial before help
    builder.button(
        text="📖 Tutorial",
        callback_data="menu:tutorial",
        style=STYLE_PRIMARY,
    )
    builder.button(text="❓ Help", callback_data="menu:help")
    # Row 4
    builder.button(text="📊 Statistics", callback_data="menu:stats")
    builder.button(text="⚡ Approval", callback_data="menu:approval")
    # Row 5
    builder.button(text="💳 Plan", callback_data="menu:plan")
    builder.button(text="🔄 Refresh", callback_data="menu:refresh")

    builder.adjust(2, 2, 2, 2, 2)

    if is_super_admin:
        # builder.button() returns the builder, not a button. The correct
        # way to add a single button on its own row is to call .button()
        # first, then .row() with no args — that just finalizes the
        # current row.
        builder.button(text="👑 Admin Panel", callback_data="admin:main")
        builder.row()

    return builder.as_markup()

ADMIN_PERMS = (
    "post_messages+edit_messages+promote_members+delete_messages+"
    "restrict_members+invite_users+pin_messages+manage_video_chats+change_info"
)


def welcome_start_keyboard(bot_username: str = "") -> InlineKeyboardMarkup:
    """
    Keyboard shown on /start before any chats connected.

    The two URL buttons use Telegram's deep-link parameters:
      ?startgroup&admin=...  → bot is added as admin of a group with rights
      ?startchannel&admin=... → bot is added as admin of a channel with rights
    If we don't know the bot username yet (e.g. getMe failed at startup),
    those rows are dropped so the keyboard still renders.
    """
    builder = InlineKeyboardBuilder()

    # Row 1: Add to Group / Add to Channel (deep-link buttons with pre-enabled rights).
    # These are the primary conversion path — keep them visible.
    if bot_username:
        builder.button(
            text="➕ Add to Group",
            url=f"https://t.me/{bot_username}?startgroup&admin={ADMIN_PERMS}",
        )
        builder.button(
            text="➕ Add to Channel",
            url=f"https://t.me/{bot_username}?startchannel&admin={ADMIN_PERMS}",
        )

    # Row 2: secondary actions
    builder.button(
        text="📖 Setup Tutorial",
        callback_data="tutorial:1",
        style=STYLE_PRIMARY,
    )
    builder.button(text="🔄 Refresh Chats", callback_data="menu:refresh")

    if bot_username:
        builder.adjust(2, 2)
    else:
        builder.adjust(2)
    return builder.as_markup()
