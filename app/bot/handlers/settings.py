from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from ..keyboards.main_menu import main_menu_keyboard
from app.core.logging import get_logger

router = Router()
logger = get_logger('settings')


@router.message(Command('settings'))
async def settings_command(message: Message, chat_repo, is_super_admin: bool):
    """
    /settings is an alias for the main menu.
    Per-chat configuration lives inside each menu entry
    (Welcome / Goodbye / Stats / Broadcast), each of which shows the
    chat picker.
    """
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    text = (
        "⚙️ <b>Settings & Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>\n"
        "Pick a section to configure:"
    )
    await message.answer(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))


@router.callback_query(F.data == 'menu:settings')
async def settings_menu(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    text = (
        "⚙️ <b>Settings & Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))
    await callback.answer()
