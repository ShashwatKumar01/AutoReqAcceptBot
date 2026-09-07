from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def chat_list_keyboard(chats: list[dict]) -> InlineKeyboardMarkup:
    """List of connected chats, each as a row with chat name."""
    builder = InlineKeyboardBuilder()

    for chat in chats:
        title = chat.get('title', 'Unknown Chat')
        # chats collection uses 'chat_id' as the key; older code read 'id'.
        chat_id = chat.get('chat_id', chat.get('id'))
        builder.button(text=f"💬 {title} →", callback_data=f"chat:select:{chat_id}")

    builder.adjust(1)

    # Bottom buttons — InlineKeyboardButton instances, not builders.
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:chats:refresh"),
        InlineKeyboardButton(text="← Back", callback_data="menu:main"),
    )

    return builder.as_markup()


def welcome_chat_picker_keyboard(chats: list[dict]) -> InlineKeyboardMarkup:
    """
    /welcome entry — let the user pick which chat to configure the welcome
    message for. Uses a different callback prefix so we don't collide with
    the generic `chat:select:` flow.
    """
    builder = InlineKeyboardBuilder()
    for chat in chats:
        title = chat.get('title', 'Unknown Chat')
        chat_id = chat.get('chat_id', chat.get('id'))
        builder.button(
            text=f"💬 {title} →",
            callback_data=f"welcome:pick:{chat_id}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="← Cancel", callback_data="menu:main"),
    )
    return builder.as_markup()


def chat_action_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Legacy per-chat action panel. No longer reached from the main flow —
    the master menu replaces it. Kept for any leftover references; the
    `← Back` button now goes to the master menu.
    """
    builder = InlineKeyboardBuilder()

    # Row 1
    builder.button(text="⚡ Approval", callback_data=f"settings:approval:{chat_id}")
    builder.button(text="👋 Welcome", callback_data=f"settings:welcome:{chat_id}")
    # Row 2
    builder.button(text="🔘 Buttons", callback_data=f"settings:buttons:{chat_id}")
    builder.button(text="📢 Broadcast", callback_data=f"broadcast:chat:{chat_id}")
    # Row 3
    builder.button(text="📊 Statistics", callback_data=f"stats:chat:{chat_id}")
    builder.button(text="🔄 Refresh", callback_data=f"chat:refresh:{chat_id}")
    # Row 4
    builder.button(text="❌ Disconnect", callback_data=f"chat:disconnect:{chat_id}")
    builder.button(text="← Back to Menu", callback_data="menu:main")

    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()
