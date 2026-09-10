from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def superadmin_main_keyboard(admin_web_url: str = "") -> InlineKeyboardMarkup:
    """Super admin main panel keyboard."""
    builder = InlineKeyboardBuilder()

    if admin_web_url:
        builder.button(text="🌐 Web Dashboard", url=admin_web_url)

    builder.button(text="👥 Users", callback_data="admin:users")
    builder.button(text="💬 Chats", callback_data="admin:chats")
    builder.button(text="📨 Join Requests", callback_data="admin:requests")
    builder.button(text="📢 Broadcasts", callback_data="admin:broadcasts")
    builder.button(text="🖥 System", callback_data="admin:system")
    builder.button(text="📢 Master Broadcast", callback_data="admin:master_broadcast")
    builder.button(text="← Exit Admin", callback_data="menu:main")

    if admin_web_url:
        builder.adjust(1, 2, 2, 2, 1)
    else:
        builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def superadmin_stats_keyboard() -> InlineKeyboardMarkup:
    """Super admin stats panel refresh keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Refresh", callback_data="admin:stats:refresh")
    builder.button(text="← Back", callback_data="admin:main")
    builder.adjust(2)
    return builder.as_markup()
