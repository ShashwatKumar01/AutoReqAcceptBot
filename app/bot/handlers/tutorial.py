from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

TUTORIAL_SECTIONS = {
    "1": {
        "title": "📱 Add the bot",
        "text": (
            "<b>Step 1 — Add as administrator</b>\n\n"
            "1. Open your <b>group</b> or <b>channel</b>\n"
            "2. <b>Manage</b> → <b>Administrators</b> → <b>Add</b>\n"
            "3. Search for {bot_mention}\n"
            "4. Enable:\n"
            "   • <b>Invite users via link</b> — required\n"
            "   • <b>Add members</b> / subscribers — required for approve\n\n"
            "5. Tap <b>Save</b>, then send <b>/start</b> to the bot in private chat."
        ),
    },
    "2": {
        "title": "🔑 Permissions",
        "text": (
            "<b>Step 2 — Why permissions matter</b>\n\n"
            "Without <b>Invite users via link</b>, Telegram will not let the bot "
            "approve join requests.\n\n"
            "<b>Optional:</b> grant enough rights so the bot can notify you if "
            "something breaks (e.g. permission removed)."
        ),
    },
    "3": {
        "title": "🔗 Join requests",
        "text": (
            "<b>Step 3 — Turn on approve-new-members</b>\n\n"
            "<b>Group / channel</b> → <b>Edit</b> → <b>Invite links</b>\n"
            "Enable <b>Approve new members</b> on the link you share.\n\n"
            "Only users who join through that flow create a "
            "<b>join request</b> the bot can handle."
        ),
    },
    "4": {
        "title": "⚡ Auto-approve",
        "text": (
            "<b>Step 4 — Approval rules</b>\n\n"
            "Open <b>/menu</b> → <b>⚡ Approval</b> → pick your chat.\n\n"
            "You can:\n"
            "• Approve <b>instantly</b>\n"
            "• Approve after a <b>delay</b> (minutes / hours)\n"
            "• Turn <b>captcha</b> on (<code>/captcha on</code> in the chat)\n"
            "• Leave requests <b>manual</b> (auto-approve off)"
        ),
    },
    "5": {
        "title": "👋 Welcome DM",
        "text": (
            "<b>Step 5 — Welcome message</b>\n\n"
            "<b>/welcome</b> or menu → <b>👋 Welcome</b>\n\n"
            "Set text, photo/video, and <b>URL buttons</b>.\n\n"
            "<b>When to send:</b>\n"
            "• On join request\n"
            "• On approval\n"
            "• After a delay\n\n"
            "Use <b>Frequency</b> for every join vs once per user."
        ),
    },
    "6": {
        "title": "🔘 Buttons & media",
        "text": (
            "<b>Step 6 — Rich welcomes</b>\n\n"
            "• <b>Buttons</b> — link to rules, channel, or website\n"
            "• <b>Media</b> — send a photo/video with caption\n"
            "• <b>Variables</b> — user name is filled automatically\n\n"
            "Tap <b>Preview</b> in the editor before saving."
        ),
    },
    "7": {
        "title": "📢 Broadcasts",
        "text": (
            "<b>Step 7 — Broadcast</b>\n\n"
            "<b>/broadcast</b> — send to members who joined through "
            "your managed chats.\n\n"
            "Progress is shown live; you can pause or cancel.\n\n"
            "<i>Telegram rate limits apply — large sends take time.</i>"
        ),
    },
    "8": {
        "title": "🔧 Troubleshooting",
        "text": (
            "<b>Step 8 — Common fixes</b>\n\n"
            "<b>Not approving?</b>\n"
            "→ Join requests ON · bot is admin · invite permission ON\n\n"
            "<b>Chat missing in menu?</b>\n"
            "→ <code>/connect &lt;chat_id&gt;</code> or re-add bot as admin\n\n"
            "<b>Welcome not received?</b>\n"
            "→ User must allow DMs; some cases only after approval\n\n"
            "<b>Need all commands?</b>\n"
            "→ Send <b>/help</b>"
        ),
    },
}

SECTION_LABELS = {
    "1": "Add bot",
    "2": "Permissions",
    "3": "Join requests",
    "4": "Auto-approve",
    "5": "Welcome",
    "6": "Buttons",
    "7": "Broadcast",
    "8": "Troubleshoot",
}


def _format_section(section: str, bot_username: str = "") -> str:
    data = TUTORIAL_SECTIONS[section]
    mention = f"@{bot_username}" if bot_username else "your bot"
    body = data["text"].format(bot_mention=mention)
    total = len(TUTORIAL_SECTIONS)
    header = f"<b>{data['title']}</b>  ·  <i>{section}/{total}</i>"
    return f"{header}\n\n{body}"


def tutorial_keyboard(section: str) -> InlineKeyboardMarkup:
    current = int(section)
    total = len(TUTORIAL_SECTIONS)
    builder = InlineKeyboardBuilder()

    if current > 1:
        builder.button(text="◀️ Previous", callback_data=f"tutorial:{current - 1}")
    if current < total:
        builder.button(text="Next ▶️", callback_data=f"tutorial:{current + 1}")
    if current > 1 and current < total:
        builder.adjust(2)
    else:
        builder.adjust(1)

    builder.row(
        InlineKeyboardButton(text="📑 All steps", callback_data="tutorial:index"),
        InlineKeyboardButton(text="❓ /help", callback_data="menu:help"),
    )
    builder.row(
        InlineKeyboardButton(text="← Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def tutorial_index_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in sorted(TUTORIAL_SECTIONS.keys(), key=int):
        label = SECTION_LABELS.get(key, key)
        builder.button(text=f"{key}. {label}", callback_data=f"tutorial:{key}")
    builder.adjust(2, 2, 2, 2)
    builder.row(
        InlineKeyboardButton(text="← Back to step 1", callback_data="tutorial:1"),
    )
    return builder.as_markup()


async def send_tutorial(message: Message, section: str = "1", bot_username: str = "") -> None:
    text = _format_section(section, bot_username)
    await message.answer(text, reply_markup=tutorial_keyboard(section))


async def edit_tutorial(callback: CallbackQuery, section: str, bot_username: str = "") -> None:
    text = _format_section(section, bot_username)
    await callback.message.edit_text(text, reply_markup=tutorial_keyboard(section))


@router.message(Command("tutorial"))
async def tutorial_command(message: Message, bot_username: str = ""):
    await send_tutorial(message, "1", bot_username)


@router.callback_query(F.data == "menu:tutorial")
async def tutorial_menu(callback: CallbackQuery, bot_username: str = ""):
    await edit_tutorial(callback, "1", bot_username)
    await callback.answer()


@router.callback_query(F.data == "tutorial:index")
async def tutorial_index(callback: CallbackQuery):
    text = (
        "<b>📑 Tutorial — pick a step</b>\n\n"
        "Follow in order the first time, or jump to any topic."
    )
    await callback.message.edit_text(
        text,
        reply_markup=tutorial_index_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tutorial:"))
async def tutorial_navigate(callback: CallbackQuery, bot_username: str = ""):
    section = callback.data.split(":", 1)[1]
    if section == "index":
        return
    if section not in TUTORIAL_SECTIONS:
        return await callback.answer("Section not found.", show_alert=True)

    await edit_tutorial(callback, section, bot_username)
    await callback.answer()
