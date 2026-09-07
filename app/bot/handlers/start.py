from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from ..keyboards.main_menu import main_menu_keyboard, welcome_start_keyboard

router = Router()

@router.message(CommandStart())
async def start_handler(
    message: Message,
    user_repo,
    chat_repo,
    is_super_admin: bool,
    bot_username: str = "",
):
    """
    1. Register/update user (done via AuthMiddleware)
    2. Show welcome message with main menu keyboard
    3. If user has connected chats: show My Chats summary
    4. If new user: show setup tutorial prompt + Add to Group/Channel deep-links
    """
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)

    if not chats:
        text = (
            "👋 <b>Welcome to Auto Request Manager!</b>\n\n"
            "I can automatically accept join requests to your Telegram groups "
            "and channels and DM new members a welcome message (with photos, "
            "videos, and premium emoji).\n\n"
            "<b>To get started, add me to a group or channel:</b>"
        )
        await message.answer(text, reply_markup=welcome_start_keyboard(bot_username=bot_username))
    else:
        text = (
            "👋 <b>Welcome back to Auto Request Manager!</b>\n\n"
            f"You have <b>{len(chats)}</b> connected chats.\n"
            "What would you like to do?"
        )
        await message.answer(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))
        # Also re-surface the Add buttons as a follow-up so growing users can
        # add another chat without leaving the menu.
        if bot_username:
            await message.answer(
                "Need to add another chat?",
                reply_markup=welcome_start_keyboard(bot_username=bot_username),
            )

@router.message(Command('help'))
async def help_handler(message: Message):
    """Show help text with all commands."""
    help_text = (
        "❓ <b>Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/tutorial - View the setup tutorial\n"
        "/mychannels - List your connected chats\n"
        "/settings - Bot settings\n"
        "/welcome - Configure welcome message for a chat\n"
        "/goodbye - Configure goodbye message for a chat\n"
        "/stats - View statistics\n"
        "/broadcast - Send broadcast message\n"
        "/plan - View your plan\n"
        "/captcha on|off - Toggle captcha verification (admins only)\n"
    )
    await message.answer(help_text)

@router.callback_query(F.data == 'menu:main')
async def main_menu_callback(
    callback: CallbackQuery,
    chat_repo,
    is_super_admin: bool,
    bot_username: str = "",
):
    """Return to main menu from any submenu."""
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)

    if not chats:
        text = (
            "👋 <b>Welcome to Auto Request Manager!</b>\n\n"
            "To get started, please add me to a group or channel."
        )
        await callback.message.edit_text(text, reply_markup=welcome_start_keyboard(bot_username=bot_username))
    else:
        text = (
            "👋 <b>Welcome back to Auto Request Manager!</b>\n\n"
            f"You have <b>{len(chats)}</b> connected chats.\n"
            "What would you like to do?"
        )
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))

@router.callback_query(F.data == 'admin:main')
@router.callback_query(F.data == 'menu:admin')
async def admin_panel_from_menu(callback: CallbackQuery, is_super_admin: bool):
    if not is_super_admin:
        return await callback.answer("⛔ Access denied. You are not a super admin.", show_alert=True)
    from ..keyboards.superadmin_menu import superadmin_main_keyboard
    await callback.message.edit_text(
        "👑 <b>Super Admin Panel</b>\n\nSelect an option to manage the system:",
        reply_markup=superadmin_main_keyboard()
    )
    await callback.answer()
