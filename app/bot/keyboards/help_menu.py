from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.styled import STYLE_PRIMARY


def help_keyboard() -> InlineKeyboardMarkup:
    """Tutorial first, then back to menu."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📖 Open tutorial",
        callback_data="tutorial:1",
        style=STYLE_PRIMARY,
    )
    builder.button(text="📋 Main menu", callback_data="menu:main")
    builder.adjust(1, 1)
    return builder.as_markup()
