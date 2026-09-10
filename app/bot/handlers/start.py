from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..keyboards.main_menu import main_menu_keyboard, welcome_start_keyboard
from ..keyboards.help_menu import help_keyboard
from ..keyboards.styled import STYLE_PRIMARY
from ..texts.help_content import build_help_text
from app.core.config import get_settings

router = Router()

_START_HINT = (
    "\n\n📖 New? See <b>/tutorial</b> for setup.\n"
    "📋 All commands: <b>/help</b>"
)

_SUPER_ADMIN_START = (
    "\n\n👑 <b>Super admin</b>\n"
    "• <b>/admin</b> — panel & web dashboard\n"
    "• <b>/master_broadcast</b> — message all bot users\n"
    "• Broadcast start & finish alerts are sent here in DM"
)


def _start_keyboard(has_chats: bool, bot_username: str, is_super_admin: bool):
    """
    /start output keyboard.

    - Always primary: Add to Group / Add to Channel (deep-links).
    - If the user already has chats connected, also show a single
      "📋 Open Menu" button that opens the full main menu.
    - Super admin: also show "👑 Admin Panel" button.
    """
    builder = InlineKeyboardBuilder()
    if bot_username:
        builder.button(
            text="➕ Add to Group",
            url=f"https://t.me/{bot_username}?startgroup=true",
        )
        builder.button(
            text="➕ Add to Channel",
            url=f"https://t.me/{bot_username}?startchannel=true",
        )
    if has_chats:
        builder.button(
            text="📋 Open Menu",
            callback_data="menu:open",
            style=STYLE_PRIMARY,
        )
    if is_super_admin:
        builder.button(text="👑 Admin Panel", callback_data="admin:main")
    if bot_username and has_chats:
        builder.adjust(2, 1, 1)
    elif bot_username:
        builder.adjust(2)
    else:
        builder.adjust(1, 1, 1)
    return builder.as_markup()


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
    2. /start is intentionally minimal — only "Add to Group / Add to Channel".
       Use 📋 Open Menu (or /menu) for the full setup.
    """
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    has_chats = bool(chats)

    if not has_chats:
        text = (
            "👋 <b>Welcome to Auto Request Manager!</b>\n\n"
            "I automatically <b>approve join requests</b> for your groups and channels "
            "and can <b>DM welcome messages</b> (text, media, buttons).\n\n"
            "<b>To get started, add me as admin:</b>"
            f"{_START_HINT}"
        )
    else:
        text = (
            f"👋 You're connected to <b>{len(chats)}</b> chat(s).\n"
            "Add another or open the menu to configure."
            f"{_START_HINT}"
        )
    if is_super_admin:
        text += _SUPER_ADMIN_START
        url = get_settings().admin_web_url
        text += f"\n🌐 Web: <code>{url}</code>"
    await message.answer(text, reply_markup=_start_keyboard(has_chats, bot_username, is_super_admin))


@router.callback_query(F.data == "menu:open")
async def open_menu_callback(callback: CallbackQuery, chat_repo, is_super_admin: bool):
    """Open the full main menu from /start."""
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    text = (
        "📋 <b>Main Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))
    await callback.answer()


@router.message(Command("menu"))
async def menu_command(message: Message, chat_repo, is_super_admin: bool):
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    text = (
        "📋 <b>Main Menu</b>\n\n"
        f"Connected chats: <b>{len(chats)}</b>"
    )
    await message.answer(text, reply_markup=main_menu_keyboard(is_super_admin=is_super_admin))

async def _reply_help(target: Message, is_super_admin: bool) -> None:
    await target.answer(
        build_help_text(is_super_admin=is_super_admin),
        reply_markup=help_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message, is_super_admin: bool = False):
    await _reply_help(message, is_super_admin)


@router.callback_query(F.data == "menu:help")
async def help_menu_callback(callback: CallbackQuery, is_super_admin: bool = False):
    await callback.message.edit_text(
        build_help_text(is_super_admin=is_super_admin),
        reply_markup=help_keyboard(),
    )
    await callback.answer()

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
    from app.core.config import get_settings
    from ..keyboards.superadmin_menu import superadmin_main_keyboard
    url = get_settings().admin_web_url
    await callback.message.edit_text(
        "👑 <b>Super Admin Panel</b>\n\n"
        "Use the bot panel or open the 🌐 Web Dashboard for full control.\n\n"
        f"Dashboard: <code>{url}</code>",
        reply_markup=superadmin_main_keyboard(url),
    )
    await callback.answer()
