from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def broadcast_picker_keyboard(chats: list[dict], is_super_admin: bool = False) -> InlineKeyboardMarkup:
    """Picker for broadcast audience — all delivery is via private DM."""
    builder = InlineKeyboardBuilder()

    if is_super_admin:
        builder.button(
            text="👥 All users + admins (DM)",
            callback_data="broadcast:pick:all_users_and_admins",
        )
        builder.button(text="🛡 All chat admins only (DM)", callback_data="broadcast:pick:chat_admins")
        builder.button(
            text="👤 Members of one chat (no admins, DM)",
            callback_data="broadcast:pick:manual_noadmins",
        )
        builder.button(
            text="🔢 Specific user / chat ID (DM)",
            callback_data="broadcast:pick:specific_id",
        )
    else:
        builder.button(text="👥 All members (my chats, DM)", callback_data="broadcast:pick:all")
        builder.button(text="🛡 Chat admins (my chats, DM)", callback_data="broadcast:pick:chat_admins")

    for chat in chats:
        title = chat.get('title', 'Unknown Chat')
        chat_id = chat.get('chat_id')
        if is_super_admin:
            builder.button(
                text=f"📢 {title} (members, no admins)",
                callback_data=f"broadcast:pick:noadmins:{chat_id}",
            )
        else:
            builder.button(text=f"📢 {title}", callback_data=f"broadcast:pick:chat:{chat_id}")

    if not is_super_admin:
        builder.button(text="🔢 Enter chat ID", callback_data="broadcast:pick:manual")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="← Back", callback_data="menu:main"))
    return builder.as_markup()
