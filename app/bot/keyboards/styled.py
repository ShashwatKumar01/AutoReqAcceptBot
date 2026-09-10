"""Colored inline callback buttons (Telegram Bot API + aiogram ButtonStyle).

Only use on callback_data buttons — not on url= deep links. Telegram rejects
LINK style on inline keyboards; URL buttons should omit style.
"""

from aiogram.enums import ButtonStyle

__all__ = ["ButtonStyle", "STYLE_PRIMARY", "STYLE_SUCCESS", "STYLE_DANGER"]

STYLE_PRIMARY = ButtonStyle.PRIMARY
STYLE_SUCCESS = ButtonStyle.SUCCESS
STYLE_DANGER = ButtonStyle.DANGER
