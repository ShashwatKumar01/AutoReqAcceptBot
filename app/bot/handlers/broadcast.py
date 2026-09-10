from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import uuid

from app.core.utils import build_broadcast_payload
from app.core.config import get_settings
from app.services.broadcast_admin_notify import (
    notify_broadcast_finished_if_needed,
    notify_broadcast_started,
)
from app.services.broadcast_status_message import (
    attach_status_message,
    format_broadcast_status_text,
    refresh_broadcast_status_message,
)
from ..keyboards.broadcast_menu import broadcast_picker_keyboard, broadcast_confirm_keyboard, broadcast_control_keyboard

class BroadcastStates(StatesGroup):
    picking_target = State()
    composing_message = State()
    confirming = State()

router = Router()

@router.message(Command('broadcast'))
async def broadcast_command(message: Message, state: FSMContext, chat_repo):
    user_id = message.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await message.answer("You don't have any connected chats.")
    
    await state.set_state(BroadcastStates.picking_target)
    await message.answer("Select a target for the broadcast:", reply_markup=broadcast_picker_keyboard(chats))

@router.callback_query(F.data == 'menu:broadcast')
async def broadcast_menu(callback: CallbackQuery, state: FSMContext, chat_repo):
    user_id = callback.from_user.id
    chats = await chat_repo.get_by_admin(user_id)
    if not chats:
        return await callback.answer("You don't have any connected chats.", show_alert=True)
    
    await state.set_state(BroadcastStates.picking_target)
    await callback.message.edit_text("Select a target for the broadcast:", reply_markup=broadcast_picker_keyboard(chats))
    await callback.answer()

@router.callback_query(BroadcastStates.picking_target, F.data.startswith('broadcast:pick:'))
async def process_broadcast_pick(callback: CallbackQuery, state: FSMContext):
    target_val = callback.data.split(':')[2]
    
    if target_val == 'all':
        await state.update_data(target='all', target_id=None)
    else:
        await state.update_data(target='chat', target_id=int(target_val))
        
    await state.set_state(BroadcastStates.composing_message)
    await callback.message.edit_text("Please send the message you want to broadcast (text, photo, video, document, etc.):")
    await callback.answer()

@router.callback_query(F.data.startswith('broadcast:chat:'))
async def broadcast_chat_start(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(':')[2])
    await state.update_data(target='chat', target_id=chat_id)
    await state.set_state(BroadcastStates.composing_message)
    await callback.message.edit_text("Please send the message you want to broadcast to this chat's users:")
    await callback.answer()

@router.message(BroadcastStates.composing_message)
async def receive_broadcast_message(message: Message, state: FSMContext, join_request_repo, chat_repo):
    payload = build_broadcast_payload(message)
    if not payload:
        return await message.answer(
            "Unsupported message type. Send text, photo, video, GIF, or document."
        )

    await state.update_data(payload=payload)
    
    data = await state.get_data()
    target = data.get('target')
    target_id = data.get('target_id')
    
    user_id = message.from_user.id
    
    estimate = 0
    if target == 'all':
        chats = await chat_repo.get_by_admin(user_id)
        for c in chats:
            c_id = c['chat_id']
            count = await join_request_repo.collection.count_documents(
                {"chat_id": c_id, "status": "approved"}
            )
            estimate += count
    else:
        estimate = await join_request_repo.collection.count_documents(
            {"chat_id": target_id, "status": "approved"}
        )
    
    await state.update_data(estimate=estimate)
    await state.set_state(BroadcastStates.confirming)
    
    job_id = str(uuid.uuid4())
    await state.update_data(job_id=job_id)
    
    target_label = "All Channels" if target == 'all' else "Specific Channel"
    text = (
        f"📊 <b>Broadcast Summary</b>\n\n"
        f"Target: {target_label}\n"
        f"Estimated recipients: {estimate}\n\n"
        "Are you ready to start?"
    )
    await message.answer(text, reply_markup=broadcast_confirm_keyboard(job_id))

@router.callback_query(BroadcastStates.confirming, F.data.startswith('broadcast:confirm:'))
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, broadcast_repo):
    data = await state.get_data()
    job_id = data['job_id']
    target = data.get('target')
    target_id = data.get('target_id')
    payload = data.get('payload')
    estimate = data.get('estimate', 0)
    
    await broadcast_repo.create_job({
        '_id': job_id,
        'owner_id': callback.from_user.id,
        'target': target,
        'target_id': target_id,
        'payload': payload,
        'status': 'running',
        'recipients_prepared': False,
        'sent_count': 0,
        'failed_count': 0,
        'total_recipients': estimate,
    })
    
    await state.clear()

    job = await broadcast_repo.get_job(job_id) or {
        "_id": job_id,
        "status": "running",
        "sent_count": 0,
        "failed_count": 0,
        "total_recipients": estimate,
    }
    text = format_broadcast_status_text(job)
    await callback.message.edit_text(text, reply_markup=broadcast_control_keyboard(job_id, "running"))
    await attach_status_message(
        broadcast_repo, job_id, callback.message.chat.id, callback.message.message_id,
    )
    job_row = await broadcast_repo.get_job(job_id) or {
        "_id": job_id,
        "target": target,
        "target_id": target_id,
        "total_recipients": estimate,
    }
    await notify_broadcast_started(
        callback.bot, get_settings(), job_row, callback.from_user.id,
    )
    await callback.answer()

@router.callback_query(F.data == 'broadcast:cancel_flow')
async def cancel_broadcast_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Broadcast cancelled.")
    await callback.answer()

# Controls
@router.callback_query(F.data.startswith('broadcast:pause:'))
async def pause_via_button(callback: CallbackQuery, broadcast_repo):
    job_id = callback.data.split(':')[2]
    await broadcast_repo.update_job_status(job_id, 'paused')
    await refresh_broadcast_status_message(callback.bot, broadcast_repo, job_id)
    await callback.answer("Paused")

@router.callback_query(F.data.startswith('broadcast:resume:'))
async def resume_via_button(callback: CallbackQuery, broadcast_repo):
    job_id = callback.data.split(':')[2]
    await broadcast_repo.update_job_status(job_id, 'running')
    await refresh_broadcast_status_message(callback.bot, broadcast_repo, job_id)
    await callback.answer("Resumed")

@router.callback_query(F.data.startswith('broadcast:cancel:'))
async def cancel_via_button(callback: CallbackQuery, broadcast_repo):
    job_id = callback.data.split(':')[2]
    await broadcast_repo.update_job_status(job_id, 'cancelled')
    await refresh_broadcast_status_message(callback.bot, broadcast_repo, job_id)
    await notify_broadcast_finished_if_needed(
        callback.bot, get_settings(), broadcast_repo, job_id,
    )
    await callback.answer("Cancelled")

@router.callback_query(F.data.startswith('broadcast:refresh_status:'))
async def refresh_broadcast_status(callback: CallbackQuery, broadcast_repo):
    job_id = callback.data.split(':')[2]
    job = await broadcast_repo.get_job(job_id)
    if not job:
        return await callback.answer("Job not found.")
    await refresh_broadcast_status_message(callback.bot, broadcast_repo, job_id)
    await callback.answer("Refreshed!")
