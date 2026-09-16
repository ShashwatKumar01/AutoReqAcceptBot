from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from ..keyboards.chat_menu import chat_list_keyboard, chat_action_keyboard
from ..filters.is_admin import IsChatAdmin

router = Router()

@router.message(Command('mychannels'))
@router.message(Command('refresh'))
async def my_chats_handler(message: Message, chat_repo):
    """Show list of connected chats."""
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    
    if not chats:
        await message.answer("You don't have any connected chats. Add me as admin to a group or channel to see it here.")
        return
        
    await message.answer(
        "Here are your connected chats. Select one to manage:",
        reply_markup=chat_list_keyboard(chats)
    )

@router.callback_query(F.data == 'menu:chats')
@router.callback_query(F.data == 'menu:chats:refresh')
@router.callback_query(F.data == 'menu:refresh')
async def chats_menu_callback(callback: CallbackQuery, chat_repo):
    """Show chats from main menu. Also handles the Refresh button."""
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)

    if not chats:
        await callback.answer("No connected chats yet.", show_alert=True)
        await callback.message.edit_text(
            "You don't have any connected chats yet.\n"
            "Add me to a group/channel as admin to get started."
        )
        return

    await callback.message.edit_text(
        "Here are your connected chats:",
        reply_markup=chat_list_keyboard(chats)
    )
    await callback.answer()

@router.callback_query(F.data.startswith('chat:select:'))
async def select_chat_callback(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    chat_id = int(callback.data.split(':')[2])
    chat = await chat_repo.get(chat_id)
    if not chat:
        return await callback.answer("Chat not found.", show_alert=True)
    title = chat.get("title", chat_id)
    from ..keyboards.chat_menu import chat_action_keyboard
    await callback.message.edit_text(
        f"⚙️ <b>Settings</b> — <b>{title}</b>\n\n"
        "Choose what to configure for this chat:",
        reply_markup=chat_action_keyboard(chat_id),
    )
    await callback.answer()

@router.callback_query(F.data.startswith('chat:refresh:'))
async def refresh_single_chat(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    """Legacy — re-renders the master menu."""
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    from ..keyboards.main_menu import main_menu_keyboard
    text = (
        "📋 <b>Main Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))
    except Exception:
        pass
    await callback.answer("Refreshed.")


@router.callback_query(F.data.startswith('chat:disconnect:'))
async def disconnect_chat(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    """Disconnect a chat, then return to the master menu."""
    parts = callback.data.split(':')
    if len(parts) > 3 and parts[2] == 'confirm':
        chat_id = int(parts[3])
        await chat_repo.record_disconnect_request(chat_id, callback.from_user.id)
        await callback.answer("Disconnected from panel (bot stays in chat).")
    else:
        chat_id = int(parts[2])
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="⚠️ Confirm", callback_data=f"chat:disconnect:confirm:{chat_id}")
        b.button(text="← Cancel", callback_data=f"settings:hub:{chat_id}")
        b.adjust(1)
        await callback.message.edit_text(
            "Disconnect this chat from <b>your admin panel</b>?\n\n"
            "• The bot <b>stays</b> in the group/channel until the owner removes it.\n"
            "• Join-request handling stops for this chat until you reconnect.\n"
            "• Your request will be saved in the database.",
            reply_markup=b.as_markup(),
        )
        return

    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    from ..keyboards.main_menu import main_menu_keyboard
    text = (
        "📋 <b>Main Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))
    except Exception:
        pass
