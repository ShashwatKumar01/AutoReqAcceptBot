from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.message(Command('stats'))
async def stats_command(message: Message, chat_repo, join_request_repo):
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    
    if not chats:
        return await message.answer("You don't have any connected chats.")
        
    if len(chats) == 1:
        # Show stats directly
        chat_id = chats[0]['chat_id']
        await show_stats(message, chat_id, chat_repo, join_request_repo)
    else:
        # Show selector
        b = InlineKeyboardBuilder()
        for c in chats:
            b.button(text=c.get('title', 'Chat'), callback_data=f"stats:chat:{c['chat_id']}")
        b.button(text="← Back to Menu", callback_data="menu:main")
        b.adjust(1)
        await message.answer("Select a chat to view stats:", reply_markup=b.as_markup())

@router.callback_query(F.data == 'menu:stats')
async def stats_menu(callback: CallbackQuery, chat_repo, join_request_repo):
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await callback.answer("You don't have any connected chats.", show_alert=True)
        
    if len(chats) == 1:
        chat_id = chats[0]['chat_id']
        await show_stats_cb(callback, chat_id, chat_repo, join_request_repo)
    else:
        b = InlineKeyboardBuilder()
        for c in chats:
            b.button(text=c.get('title', 'Chat'), callback_data=f"stats:chat:{c['chat_id']}")
        b.button(text="← Back to Menu", callback_data="menu:main")
        b.adjust(1)
        await callback.message.edit_text("Select a chat to view stats:", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith('stats:chat:'))
async def chat_stats_callback(callback: CallbackQuery, chat_repo, join_request_repo):
    chat_id = int(callback.data.split(':')[2])
    await show_stats_cb(callback, chat_id, chat_repo, join_request_repo)

@router.callback_query(F.data.startswith('stats:refresh:'))
async def refresh_stats(callback: CallbackQuery, chat_repo, join_request_repo):
    chat_id = int(callback.data.split(':')[2])
    await show_stats_cb(callback, chat_id, chat_repo, join_request_repo)
    await callback.answer("Stats refreshed!")

async def get_real_stats(chat_id: int, chat_repo, join_request_repo):
    chat = await chat_repo.get(chat_id)
    if not chat:
        return None
        
    total_reqs = await join_request_repo.collection.count_documents({"chat_id": chat_id})
    approved_reqs = await join_request_repo.collection.count_documents({"chat_id": chat_id, "status": "approved"})
    declined_reqs = await join_request_repo.collection.count_documents({"chat_id": chat_id, "status": "declined"})
    welcome_sent = chat.get('total_welcome_sent', 0)
    
    return chat, total_reqs, approved_reqs, declined_reqs, welcome_sent

async def show_stats(message: Message, chat_id: int, chat_repo, join_request_repo):
    res = await get_real_stats(chat_id, chat_repo, join_request_repo)
    if not res:
        return await message.answer("Chat not found.")
    
    chat, total_reqs, approved_reqs, declined_reqs, welcome_sent = res
        
    text = (
        f"📊 <b>Stats for {chat.get('title')}</b>\n\n"
        f"Total Requests: {total_reqs}\n"
        f"Approved: {approved_reqs}\n"
        f"Declined: {declined_reqs}\n"
        f"Welcome Messages Sent: {welcome_sent}"
    )
    
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Refresh", callback_data=f"stats:refresh:{chat_id}")
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)

    await message.answer(text, reply_markup=b.as_markup())

async def show_stats_cb(callback: CallbackQuery, chat_id: int, chat_repo, join_request_repo):
    res = await get_real_stats(chat_id, chat_repo, join_request_repo)
    if not res:
        return await callback.answer("Chat not found.")
        
    chat, total_reqs, approved_reqs, declined_reqs, welcome_sent = res
        
    text = (
        f"📊 <b>Stats for {chat.get('title')}</b>\n\n"
        f"Total Requests: {total_reqs}\n"
        f"Approved: {approved_reqs}\n"
        f"Declined: {declined_reqs}\n"
        f"Welcome Messages Sent: {welcome_sent}"
    )
    
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Refresh", callback_data=f"stats:refresh:{chat_id}")
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)

    await callback.message.edit_text(text, reply_markup=b.as_markup())
