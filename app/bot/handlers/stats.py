from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


async def get_real_stats(chat_id: int, chat_repo, join_request_repo):
    chat = await chat_repo.get(chat_id)
    if not chat:
        return None

    total_reqs = await join_request_repo.collection.count_documents({"chat_id": chat_id})
    approved_reqs = await join_request_repo.collection.count_documents(
        {"chat_id": chat_id, "status": "approved"}
    )
    pending_reqs = await join_request_repo.collection.count_documents(
        {"chat_id": chat_id, "status": {"$in": ["pending", "scheduled"]}}
    )
    declined_reqs = await join_request_repo.collection.count_documents(
        {"chat_id": chat_id, "status": "declined"}
    )
    welcome_sent = chat.get('total_welcome_sent', 0)

    return chat, total_reqs, approved_reqs, pending_reqs, declined_reqs, welcome_sent


def _chat_type_label(chat: dict) -> str:
    chat_type = chat.get("type", "chat")
    if chat_type == "channel":
        return "📢 Channel"
    if chat_type in ("group", "supergroup"):
        return "👥 Group"
    return "💬 Chat"


async def _format_channel_stats(chat: dict, stats) -> str:
    chat, total_reqs, approved_reqs, pending_reqs, declined_reqs, welcome_sent = stats
    title = chat.get("title", "Unknown")
    chat_type = _chat_type_label(chat)
    return (
        f"<b>{title}</b> ({chat_type})\n"
        f"  Requests: {total_reqs} | Approved: {approved_reqs} | "
        f"Pending: {pending_reqs} | Declined: {declined_reqs}\n"
        f"  Welcome sent: {welcome_sent}"
    )


async def _build_overview_text(chats: list, chat_repo, join_request_repo) -> str:
    lines = ["📊 <b>Statistics — All Channels</b>\n"]
    totals = {"requests": 0, "approved": 0, "pending": 0, "declined": 0, "welcome": 0}

    for c in chats:
        chat_id = c["chat_id"]
        res = await get_real_stats(chat_id, chat_repo, join_request_repo)
        if not res:
            continue
        chat, total_reqs, approved_reqs, pending_reqs, declined_reqs, welcome_sent = res
        totals["requests"] += total_reqs
        totals["approved"] += approved_reqs
        totals["pending"] += pending_reqs
        totals["declined"] += declined_reqs
        totals["welcome"] += welcome_sent
        lines.append(await _format_channel_stats(chat, res))
        lines.append("")

    lines.append(
        "<b>Total across all channels:</b>\n"
        f"Requests: {totals['requests']} | Approved: {totals['approved']} | "
        f"Pending: {totals['pending']} | Declined: {totals['declined']}\n"
        f"Welcome sent: {totals['welcome']}"
    )
    return "\n".join(lines)


def _stats_keyboard(chats: list, show_overview: bool = True) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    if show_overview and len(chats) > 1:
        b.button(text="📊 All Channels Overview", callback_data="stats:overview")
    for c in chats:
        title = c.get('title', 'Chat')
        chat_id = c['chat_id']
        b.button(text=f"📈 {title}", callback_data=f"stats:chat:{chat_id}")
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)
    return b


@router.message(Command('stats'))
async def stats_command(message: Message, chat_repo, join_request_repo):
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)

    if not chats:
        return await message.answer("You don't have any connected chats.")

    if len(chats) == 1:
        chat_id = chats[0]['chat_id']
        await show_stats(message, chat_id, chat_repo, join_request_repo, multi_chat=False)
    else:
        text = await _build_overview_text(chats, chat_repo, join_request_repo)
        await message.answer(text, reply_markup=_stats_keyboard(chats).as_markup())


@router.callback_query(F.data == 'menu:stats')
async def stats_menu(callback: CallbackQuery, chat_repo, join_request_repo):
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await callback.answer("You don't have any connected chats.", show_alert=True)

    if len(chats) == 1:
        chat_id = chats[0]['chat_id']
        await show_stats_cb(callback, chat_id, chat_repo, join_request_repo, multi_chat=False)
    else:
        text = await _build_overview_text(chats, chat_repo, join_request_repo)
        await callback.message.edit_text(text, reply_markup=_stats_keyboard(chats).as_markup())
    await callback.answer()


@router.callback_query(F.data == 'stats:overview')
async def stats_overview_callback(callback: CallbackQuery, chat_repo, join_request_repo):
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await callback.answer("No connected chats.", show_alert=True)
    text = await _build_overview_text(chats, chat_repo, join_request_repo)
    await callback.message.edit_text(text, reply_markup=_stats_keyboard(chats).as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith('stats:chat:'))
async def chat_stats_callback(callback: CallbackQuery, chat_repo, join_request_repo):
    chat_id = int(callback.data.split(':')[2])
    await show_stats_cb(callback, chat_id, chat_repo, join_request_repo)
    await callback.answer()


@router.callback_query(F.data.startswith('stats:refresh:'))
async def refresh_stats(callback: CallbackQuery, chat_repo, join_request_repo):
    chat_id = int(callback.data.split(':')[2])
    await show_stats_cb(callback, chat_id, chat_repo, join_request_repo)
    await callback.answer("Stats refreshed!")


def _single_chat_keyboard(chat_id: int, multi_chat: bool) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Refresh", callback_data=f"stats:refresh:{chat_id}")
    if multi_chat:
        b.button(text="← All Channels", callback_data="stats:overview")
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)
    return b


async def show_stats(message: Message, chat_id: int, chat_repo, join_request_repo, multi_chat: bool = False):
    res = await get_real_stats(chat_id, chat_repo, join_request_repo)
    if not res:
        return await message.answer("Chat not found.")

    chat, total_reqs, approved_reqs, pending_reqs, declined_reqs, welcome_sent = res
    chat_type = _chat_type_label(chat)

    text = (
        f"📊 <b>Stats for {chat.get('title')}</b>\n"
        f"Type: {chat_type}\n\n"
        f"Total Requests: {total_reqs}\n"
        f"Approved: {approved_reqs}\n"
        f"Pending: {pending_reqs}\n"
        f"Declined: {declined_reqs}\n"
        f"Welcome Messages Sent: {welcome_sent}"
    )

    await message.answer(text, reply_markup=_single_chat_keyboard(chat_id, multi_chat).as_markup())


async def show_stats_cb(callback: CallbackQuery, chat_id: int, chat_repo, join_request_repo, multi_chat: bool = True):
    res = await get_real_stats(chat_id, chat_repo, join_request_repo)
    if not res:
        return await callback.answer("Chat not found.")

    chat, total_reqs, approved_reqs, pending_reqs, declined_reqs, welcome_sent = res
    chat_type = _chat_type_label(chat)

    text = (
        f"📊 <b>Stats for {chat.get('title')}</b>\n"
        f"Type: {chat_type}\n\n"
        f"Total Requests: {total_reqs}\n"
        f"Approved: {approved_reqs}\n"
        f"Pending: {pending_reqs}\n"
        f"Declined: {declined_reqs}\n"
        f"Welcome Messages Sent: {welcome_sent}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=_single_chat_keyboard(chat_id, multi_chat).as_markup(),
    )
