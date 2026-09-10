"""Colored inline/reply buttons (Telegram Bot API + aiogram ButtonStyle)."""

from aiogram.enums import ButtonStyle

# Re-export for handlers
__all__ = ["ButtonStyle", "STYLE_PRIMARY", "STYLE_SUCCESS", "STYLE_DANGER", "STYLE_LINK"]

STYLE_PRIMARY = ButtonStyle.PRIMARY
STYLE_SUCCESS = ButtonStyle.SUCCESS
STYLE_DANGER = ButtonStyle.DANGER
STYLE_LINK = ButtonStyle.LINK
