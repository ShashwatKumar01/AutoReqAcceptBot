"""
Goodbye message — sent when a member leaves a chat.

Settings (stored in chat_settings, mirroring welcome_*):
  goodbye_enabled          bool  default False
  goodbye_text             str
  goodbye_media_file_id    str
  goodbye_media_type       'photo' | 'video' | 'animation' | 'document'
  goodbye_buttons          list of {text, url, row}

Bot only DMs on member-left if the user has /started the bot; otherwise
Telegram won't let us send them a private message.
"""
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.core.logging import get_logger
# (No imports from welcome_menu — goodbye has its own chat-picker helper.)

router = Router()
logger = get_logger('goodbye')


class GoodbyeStates(StatesGroup):
    editing_text = State()
    waiting_media = State()
    waiting_btn_text = State()
    waiting_btn_url = State()


# ──────────────────────────────────────────────────────────────────────────────
# chat_member handler — fires when a user leaves a chat
# ──────────────────────────────────────────────────────────────────────────────

@router.chat_member()
async def on_member_left(
    event: ChatMemberUpdated,
    bot: Bot,
    chat_repo,
):
    """
    Send a goodbye DM when a user leaves a group/channel where the bot is
    admin. We only DMs — never posts back into the chat itself.
    """
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status
    # "left" / "kicked" / "banned" all count as the user being gone
    if new_status not in ("left", "kicked", "banned"):
        return
    if old_status in ("left", "kicked", "banned"):
        return  # already gone before

    chat_id = event.chat.id
    user = event.from_user
    if not user or user.is_bot:
        return

    settings = await chat_repo.get_chat_settings_with_defaults(chat_id)
    if not settings.get("goodbye_enabled", False):
        return

    text = settings.get("goodbye_text", "")
    media_id = settings.get("goodbye_media_file_id", "")
    media_type = settings.get("goodbye_media_type", "")
    buttons = settings.get("goodbye_buttons", [])
    if not text and not media_id:
        return

    frequency = settings.get("goodbye_frequency", "every_leave")
    if frequency == "once":
        if await chat_repo.user_received_goodbye_once(user.id, chat_id):
            logger.info(
                "Goodbye skipped — once per user",
                chat_id=chat_id, user_id=user.id,
            )
            return

    # Substitute variables
    first = user.first_name or ""
    last = user.last_name or ""
    uname = user.username or ""
    chat_title = event.chat.title or "the group"
    rendered = (
        text
        .replace("{first_name}", first)
        .replace("{last_name}", last)
        .replace("{username}", f"@{uname}" if uname else first)
        .replace("{user_id}", str(user.id))
        .replace("{chat_title}", chat_title)
    )

    # Build inline keyboard
    markup: InlineKeyboardMarkup | None = None
    if buttons:
        rows: dict[int, list] = {}
        for btn in buttons:
            row_idx = int(btn.get("row", 1))
            kwargs = {"text": str(btn.get("text", ""))[:64]}
            if btn.get("url"):
                kwargs["url"] = btn["url"]
            elif btn.get("callback_data"):
                kwargs["callback_data"] = btn["callback_data"]
            else:
                continue
            rows.setdefault(row_idx, []).append(InlineKeyboardButton(**kwargs))
        markup = InlineKeyboardMarkup(
            inline_keyboard=[rows[i] for i in sorted(rows)]
        )

    try:
        if media_id and media_type == "photo":
            await bot.send_photo(
                chat_id=user.id, photo=media_id,
                caption=rendered[:1024] or None,
                parse_mode="HTML", reply_markup=markup,
            )
        elif media_id and media_type == "video":
            await bot.send_video(
                chat_id=user.id, video=media_id,
                caption=rendered[:1024] or None,
                parse_mode="HTML", reply_markup=markup,
            )
        elif media_id and media_type == "animation":
            await bot.send_animation(
                chat_id=user.id, animation=media_id,
                caption=rendered[:1024] or None,
                parse_mode="HTML", reply_markup=markup,
            )
        elif media_id and media_type == "document":
            await bot.send_document(
                chat_id=user.id, document=media_id,
                caption=rendered[:1024] or None,
                parse_mode="HTML", reply_markup=markup,
            )
        else:
            await bot.send_message(
                chat_id=user.id, text=rendered[:4096],
                parse_mode="HTML", reply_markup=markup,
            )
        if frequency == "once":
            await chat_repo.mark_goodbye_delivered(user.id, chat_id)
        logger.info("Goodbye sent", chat_id=chat_id, user_id=user.id)
    except Exception as e:
        # The user has not started the bot (or blocked it) — Telegram
        # rejects the DM. Silent: we can't do anything about it.
        logger.info("Goodbye DM failed (user blocked / not started)",
                    chat_id=chat_id, user_id=user.id, error=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Settings loaders / renderers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_goodbye_settings(chat_repo, chat_id: int) -> dict:
    raw = await chat_repo.get_chat_settings(chat_id) or {}
    return {
        "goodbye_enabled": raw.get("goodbye_enabled", False),
        "goodbye_text": raw.get("goodbye_text", ""),
        "goodbye_media_file_id": raw.get("goodbye_media_file_id", ""),
        "goodbye_media_type": raw.get("goodbye_media_type", ""),
        "goodbye_buttons": raw.get("goodbye_buttons", []),
        "goodbye_frequency": raw.get("goodbye_frequency", "every_leave"),
    }


async def _render_editor(target, chat_repo, chat_id: int, *, edit: bool = False):
    chat = await chat_repo.get(chat_id)
    if not chat:
        txt = "❌ Chat not found."
        return await (target.edit_text(txt) if edit else target.answer(txt))

    gs = await _get_goodbye_settings(chat_repo, chat_id)
    title = chat.get("title", "this chat")

    body = (
        f"🚪 <b>Goodbye Editor — {title}</b>\n\n"
        "Sent to a member's DM when they leave this chat.\n"
        "If they have not /started the bot, Telegram won't let us DM.\n"
        "✅ marks what's already set.\n\n"
        f"<b>Frequency:</b> {_frequency_label(gs['goodbye_frequency'])}"
    )

    b = _goodbye_editor_keyboard(
        chat_id=chat_id,
        enabled=gs["goodbye_enabled"],
        has_text=bool(gs["goodbye_text"]),
        has_media=bool(gs["goodbye_media_file_id"]),
        btn_count=len(gs["goodbye_buttons"]),
        frequency=gs["goodbye_frequency"],
    )

    if edit:
        return await target.edit_text(body, reply_markup=b)
    return await target.answer(body, reply_markup=b)


def _frequency_label(freq: str) -> str:
    if freq == "once":
        return "Only once per member"
    return "Every time they leave"


def _goodbye_editor_keyboard(
    chat_id: int,
    enabled: bool,
    has_text: bool,
    has_media: bool,
    btn_count: int,
    frequency: str = "every_leave",
) -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    toggle = "✅" if enabled else "❌"
    b.button(text=f"{toggle} Goodbye", callback_data=f"goodbye:toggle:{chat_id}")
    text_icon = "✅" if has_text else "➕"
    b.button(text=f"📝 {text_icon} Message", callback_data=f"goodbye:edit_text:{chat_id}")
    media_icon = "✅" if has_media else "➕"
    b.button(text=f"🖼 {media_icon} Media", callback_data=f"goodbye:set_media:{chat_id}")
    if has_media:
        b.button(text="🗑 Clear media", callback_data=f"goodbye:remove_media:{chat_id}")
    b.button(text=f"🔘 Buttons · {btn_count}", callback_data=f"goodbye:buttons:{chat_id}")
    freq_short = "Once" if frequency == "once" else "Every leave"
    b.button(text=f"🔁 {freq_short}", callback_data=f"goodbye:freq_toggle:{chat_id}")
    b.button(text="👁 Preview", callback_data=f"goodbye:preview:{chat_id}")
    b.button(text="← Menu", callback_data="menu:main")
    if has_media:
        b.adjust(2, 2, 2, 1, 1)
    else:
        b.adjust(2, 2, 2, 1)
    return b.as_markup()


# ──────────────────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("goodbye"))
async def goodbye_command(message: Message, chat_repo):
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await message.answer(
            "You don't have any connected chats yet.\n"
            "Add me to a group or channel first via /start."
        )
    if len(chats) == 1:
        return await _render_editor(message, chat_repo, chats[0]["chat_id"])
    await message.answer(
        "🚪 <b>Goodbye Message Setup</b>\n\nSelect the group or channel to configure:",
        reply_markup=welcome_chat_picker_keyboard_with_prefix(chats, "goodbye:pick"),
    )


def welcome_chat_picker_keyboard_with_prefix(chats, prefix: str):
    """Like welcome_chat_picker_keyboard but with custom callback prefix."""
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for c in chats:
        title = c.get("title", "Chat")
        chat_id = c.get("chat_id")
        b.button(text=f"💬 {title}", callback_data=f"{prefix}:{chat_id}")
    b.button(text="← Menu", callback_data="menu:main")
    b.adjust(2, 1)
    return b.as_markup()


@router.callback_query(F.data.startswith("goodbye:pick:"))
async def goodbye_pick_chat(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "menu:goodbye")
async def goodbye_menu(callback: CallbackQuery, chat_repo):
    """Entry from main-menu button."""
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await callback.answer("You don't have any connected chats.", show_alert=True)
    if len(chats) == 1:
        await _render_editor(callback.message, chat_repo, chats[0]["chat_id"], edit=True)
        return await callback.answer()
    await callback.message.edit_text(
        "🚪 <b>Goodbye Message Setup</b>\n\nSelect the group or channel to configure:",
        reply_markup=welcome_chat_picker_keyboard_with_prefix(chats, "goodbye:pick"),
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Toggle
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goodbye:freq_toggle:"))
async def toggle_goodbye_frequency(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    new_freq = "once" if gs["goodbye_frequency"] != "once" else "every_leave"
    await chat_repo.upsert_settings(chat_id, {"goodbye_frequency": new_freq})
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer(f"Goodbye: {_frequency_label(new_freq)}")


@router.callback_query(F.data.startswith("goodbye:toggle:"))
async def toggle_goodbye(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    new_val = not gs["goodbye_enabled"]
    await chat_repo.upsert_settings(chat_id, {"goodbye_enabled": new_val})
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer(f"Goodbye {'enabled ✅' if new_val else 'disabled ❌'}")


# ──────────────────────────────────────────────────────────────────────────────
# Edit text
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goodbye:edit_text:"))
async def start_edit_text(callback: CallbackQuery, state: FSMContext, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    current = gs["goodbye_text"]
    snippet = (current[:200] + "…" if len(current) > 200 else current) if current else "(empty)"

    await state.set_state(GoodbyeStates.editing_text)
    await state.update_data(chat_id=chat_id)
    await callback.message.answer(
        "✏️ <b>Send the new goodbye message text.</b>\n\n"
        "<b>Variables:</b> <code>{first_name}</code> <code>{last_name}</code> "
        "<code>{username}</code> <code>{chat_title}</code>\n"
        "<b>HTML formatting</b> supported, including premium emoji.\n\n"
        f"<b>Current:</b>\n{snippet}\n\n"
        "Send /cancel to abort."
    )
    await callback.answer()


@router.message(GoodbyeStates.editing_text, Command("cancel"))
async def cancel_edit_text(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.")


@router.message(GoodbyeStates.editing_text)
async def receive_text(message: Message, state: FSMContext, chat_repo):
    text = message.html_text or message.text or message.caption or ""
    if not text:
        return await message.answer("Please send text. Or /cancel.")

    data = await state.get_data()
    chat_id = data["chat_id"]
    await chat_repo.upsert_settings(chat_id, {"goodbye_text": text})
    await state.clear()
    await message.answer("✅ Goodbye text saved!")
    await _render_editor(message, chat_repo, chat_id)


# ──────────────────────────────────────────────────────────────────────────────
# Set / remove media
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goodbye:set_media:"))
async def start_set_media(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[2])
    await state.set_state(GoodbyeStates.waiting_media)
    await state.update_data(chat_id=chat_id)
    await callback.message.answer(
        "🖼 <b>Send a photo, video, GIF or document</b> for the goodbye message.\n\n"
        "If you include a caption, it will <b>replace</b> the current goodbye text.\n\n"
        "Send /cancel to abort."
    )
    await callback.answer()


@router.message(GoodbyeStates.waiting_media, Command("cancel"))
async def cancel_set_media(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.")


@router.message(GoodbyeStates.waiting_media)
async def receive_media(message: Message, state: FSMContext, chat_repo):
    file_id = None
    media_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        media_type = "animation"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
    else:
        return await message.answer("Please send a photo, video, GIF or document. Or /cancel.")

    data = await state.get_data()
    chat_id = data["chat_id"]
    updates = {
        "goodbye_media_file_id": file_id,
        "goodbye_media_type": media_type,
    }
    if message.caption:
        updates["goodbye_text"] = message.html_text or message.caption
    await chat_repo.upsert_settings(chat_id, updates)
    await state.clear()
    await message.answer(f"✅ {media_type.capitalize()} saved!")
    await _render_editor(message, chat_repo, chat_id)


@router.callback_query(F.data.startswith("goodbye:remove_media:"))
async def remove_media(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    await chat_repo.upsert_settings(chat_id, {
        "goodbye_media_file_id": "",
        "goodbye_media_type": "",
    })
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer("Media removed.")


# ──────────────────────────────────────────────────────────────────────────────
# Buttons
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goodbye:buttons:"))
async def show_buttons(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    buttons = gs["goodbye_buttons"]
    await _render_buttons_panel(callback.message, chat_id, buttons, edit=True)
    await callback.answer()


async def _render_buttons_panel(target, chat_id: int, buttons: list, *, edit: bool):
    count = len(buttons)
    body = (
        f"🔘 <b>Goodbye Inline Buttons</b> ({count}/10)\n\n"
        + (
            "\n".join(
                f"{i+1}. <b>{b.get('text','')}</b> → <code>{b.get('url','')}</code>"
                for i, b in enumerate(buttons)
            )
            if buttons
            else "No buttons set yet."
        )
        + "\n\nSend buttons in the @chelpbot format:\n"
        "<code>Button text - https://t.me/link</code>\n"
        "Multiple per row: separate with <code>&amp;&amp;</code>\n"
        "New row: new line. Popup: <code>popup:Text</code>."
    )
    b = _goodbye_buttons_keyboard(chat_id, buttons)
    if edit:
        return await target.edit_text(body, reply_markup=b)
    return await target.answer(body, reply_markup=b)


def _goodbye_buttons_keyboard(chat_id: int, buttons: list) -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for i, btn in enumerate(buttons):
        label = btn.get("text", f"Button {i+1}")[:20]
        url_short = btn.get("url", "")[:25]
        b.button(
            text=f"🗑{i + 1} {label}",
            callback_data=f"goodbye:btn_remove:{chat_id}:{i}",
        )
    if len(buttons) < 10:
        b.button(text="➕ Add", callback_data=f"goodbye:btn_add:{chat_id}")
    b.button(text="← Back", callback_data=f"goodbye:edit:{chat_id}")
    b.adjust(2)
    return b.as_markup()


@router.callback_query(F.data.startswith("goodbye:btn_add:"))
async def start_add_buttons(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[2])
    await state.set_state(GoodbyeStates.waiting_btn_text)
    await state.update_data(chat_id=chat_id)
    await callback.message.answer(
        "🔘 <b>Add Buttons</b>\n\n"
        "Send in this format:\n"
        "<code>Channel - https://t.me/channel</code>\n\n"
        "Multiple in one row: <code>&amp;&amp;</code>\n"
        "Multiple rows: new line\n"
        "Popup: <code>Button - popup:Message</code>\n\n"
        "Send /cancel to abort."
    )
    await callback.answer()


@router.message(GoodbyeStates.waiting_btn_text, Command("cancel"))
async def cancel_btn(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.")


@router.message(GoodbyeStates.waiting_btn_text)
async def receive_buttons(message: Message, state: FSMContext, chat_repo):
    from app.bot.handlers.welcome import parse_button_input
    text = message.text or ""
    if not text.strip():
        return await message.answer("Please send the button text format. Or /cancel.")

    new_buttons, errors = parse_button_input(text)
    if not new_buttons:
        return await message.answer(
            f"❌ Couldn't parse. {errors}\n\nOr /cancel."
        )

    data = await state.get_data()
    chat_id = data["chat_id"]

    gs = await _get_goodbye_settings(chat_repo, chat_id)
    existing = gs["goodbye_buttons"]
    combined = existing + new_buttons
    if len(combined) > 10:
        combined = combined[:10]

    await chat_repo.upsert_settings(chat_id, {"goodbye_buttons": combined})
    await state.clear()
    await message.answer(f"✅ Added {len(new_buttons)} button(s).")
    await _render_buttons_panel(message, chat_id, combined, edit=False)


@router.callback_query(F.data.startswith("goodbye:btn_remove:"))
async def remove_button(callback: CallbackQuery, chat_repo):
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    idx = int(parts[3])
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    buttons = gs["goodbye_buttons"]
    if 0 <= idx < len(buttons):
        buttons.pop(idx)
        await chat_repo.upsert_settings(chat_id, {"goodbye_buttons": buttons})
    await _render_buttons_panel(callback.message, chat_id, buttons, edit=True)
    await callback.answer("Button removed.")


@router.callback_query(F.data.startswith("goodbye:edit:"))
async def edit_back(callback: CallbackQuery, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    await _render_editor(callback.message, chat_repo, chat_id, edit=True)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Preview
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goodbye:preview:"))
async def preview(callback: CallbackQuery, bot: Bot, chat_repo):
    chat_id = int(callback.data.split(":")[2])
    chat = await chat_repo.get(chat_id) or {}
    gs = await _get_goodbye_settings(chat_repo, chat_id)
    user = callback.from_user

    text = gs["goodbye_text"] or "👋 Goodbye!"
    rendered = (
        text
        .replace("{first_name}", user.first_name or "John")
        .replace("{last_name}", user.last_name or "Doe")
        .replace("{username}", f"@{user.username}" if user.username else "@johndoe")
        .replace("{chat_title}", chat.get("title", "Your Group"))
        .replace("{user_id}", str(user.id))
    )

    markup = None
    if gs["goodbye_buttons"]:
        rows: dict[int, list] = {}
        for btn in gs["goodbye_buttons"]:
            row_idx = int(btn.get("row", 1))
            rows.setdefault(row_idx, []).append(
                InlineKeyboardButton(text=str(btn.get("text", ""))[:64],
                                     url=btn.get("url"))
            )
        markup = InlineKeyboardMarkup(inline_keyboard=[rows[i] for i in sorted(rows)])

    media_id = gs["goodbye_media_file_id"]
    media_type = gs["goodbye_media_type"]
    try:
        if media_id and media_type == "photo":
            await bot.send_photo(chat_id=user.id, photo=media_id,
                                 caption=rendered[:1024] or None,
                                 parse_mode="HTML", reply_markup=markup)
        elif media_id and media_type == "video":
            await bot.send_video(chat_id=user.id, video=media_id,
                                 caption=rendered[:1024] or None,
                                 parse_mode="HTML", reply_markup=markup)
        elif media_id and media_type == "animation":
            await bot.send_animation(chat_id=user.id, animation=media_id,
                                     caption=rendered[:1024] or None,
                                     parse_mode="HTML", reply_markup=markup)
        elif media_id and media_type == "document":
            await bot.send_document(chat_id=user.id, document=media_id,
                                    caption=rendered[:1024] or None,
                                    parse_mode="HTML", reply_markup=markup)
        else:
            await bot.send_message(chat_id=user.id, text=rendered[:4096],
                                   parse_mode="HTML", reply_markup=markup)
        await callback.answer("👁 Preview sent ⤵️")
    except Exception as e:
        await callback.answer(f"Preview failed: {str(e)[:100]}", show_alert=True)
