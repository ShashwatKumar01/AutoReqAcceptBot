from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from ..keyboards.main_menu import main_menu_keyboard
from ..keyboards.settings_menu import settings_chat_picker_keyboard
from ..keyboards.chat_menu import chat_action_keyboard
from app.core.logging import get_logger

router = Router()
logger = get_logger('settings')


async def _show_chat_picker(target: Message | CallbackQuery, chat_repo, is_super_admin: bool, edit: bool = False):
    user_id = target.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    text = (
        "⚙️ <b>Settings</b>\n\n"
        "First, select the <b>group or channel</b> you want to manage.\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    if not chats:
        text = (
            "⚙️ <b>Settings</b>\n\n"
            "You don't have any connected chats yet.\n"
            "Add the bot as admin to a group or channel, then tap Refresh on /start."
        )
        kb = main_menu_keyboard(is_super_admin=is_super_admin)
    elif len(chats) == 1:
        chat_id = chats[0]["chat_id"]
        title = chats[0].get("title", chat_id)
        text = (
            f"⚙️ <b>Settings</b> — <b>{title}</b>\n\n"
            "Choose what to configure for this chat:"
        )
        kb = chat_action_keyboard(chat_id)
    else:
        kb = settings_chat_picker_keyboard(chats)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    elif edit:
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.message.answer(text, reply_markup=kb)


@router.message(Command('settings'))
async def settings_command(message: Message, chat_repo, is_super_admin: bool):
    await _show_chat_picker(message, chat_repo, is_super_admin)


@router.callback_query(F.data == 'menu:settings')
async def settings_menu(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    await _show_chat_picker(callback, chat_repo, is_super_admin, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('settings:hub:'))
async def settings_hub(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(':')[2])
    chat = await chat_repo.get(chat_id)
    if not chat:
        return await callback.answer("Chat not found.", show_alert=True)
    title = chat.get("title", chat_id)
    await callback.message.edit_text(
        f"⚙️ <b>Settings</b> — <b>{title}</b>\n\n"
        "Choose what to configure for this chat:",
        reply_markup=chat_action_keyboard(chat_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('settings:welcome:'))
async def settings_welcome(callback: CallbackQuery, chat_repo):
    from .welcome import _render_editor
    chat_id = int(callback.data.split(':')[2])
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer()
