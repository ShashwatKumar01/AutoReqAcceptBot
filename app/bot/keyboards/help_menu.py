from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def help_keyboard() -> InlineKeyboardMarkup:
    """Tutorial first, then back to menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Open tutorial", callback_data="tutorial:1")
    builder.button(text="📋 Main menu", callback_data="menu:main")
    builder.adjust(1, 1)
    return builder.as_markup()
