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
from app.services.broadcast_targets import estimate_recipients, TARGET_LABELS
from ..keyboards.broadcast_menu import (
    broadcast_picker_keyboard,
    broadcast_confirm_keyboard,
    broadcast_control_keyboard,
)

class BroadcastStates(StatesGroup):
    picking_target = State()
    enter_chat_id = State()
    composing_message = State()
    confirming = State()

router = Router()


async def _list_chats_for_picker(chat_repo, user_id: int, is_super_admin: bool) -> list:
    if is_super_admin:
        cursor = chat_repo.collection.find({}).sort("title", 1).limit(80)
        return await cursor.to_list(length=80)
    return await chat_repo.get_by_admin(user_id)


async def _start_broadcast_picker(message_or_callback, state: FSMContext, chat_repo, user_id: int, is_super_admin: bool):
    chats = await _list_chats_for_picker(chat_repo, user_id, is_super_admin)
    if not chats and not is_super_admin:
        text = "You don't have any connected chats."
        if isinstance(message_or_callback, Message):
            return await message_or_callback.answer(text)
        return await message_or_callback.answer(text, show_alert=True)

    await state.set_state(BroadcastStates.picking_target)
    await state.update_data(is_super_admin_broadcast=is_super_admin)
    text = "Select who should receive this broadcast:"
    kb = broadcast_picker_keyboard(chats, is_super_admin=is_super_admin)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=kb)


@router.message(Command('broadcast'))
async def broadcast_command(message: Message, state: FSMContext, chat_repo, is_super_admin: bool = False):
    if is_super_admin:
        return await _start_broadcast_picker(message, state, chat_repo, message.from_user.id, True)
    await _start_broadcast_picker(message, state, chat_repo, message.from_user.id, False)


@router.callback_query(F.data == 'menu:broadcast')
async def broadcast_menu(callback: CallbackQuery, state: FSMContext, chat_repo, is_super_admin: bool = False):
    await _start_broadcast_picker(callback, state, chat_repo, callback.from_user.id, is_super_admin)
    await callback.answer()


@router.callback_query(BroadcastStates.picking_target, F.data.startswith('broadcast:pick:'))
async def process_broadcast_pick(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_sa = data.get('is_super_admin_broadcast', False)
    user_id = callback.from_user.id
    parts = callback.data.split(':')
    action = parts[2]

    if action == 'manual':
        await state.set_state(BroadcastStates.enter_chat_id)
        await callback.message.edit_text(
            "Send the <b>chat ID</b> (e.g. <code>-1001234567890</code>):",
            parse_mode="HTML",
        )
        return await callback.answer()

    target_id = None
    scope = user_id

    if action == 'chat' and len(parts) >= 4:
        target = 'chat_members'
        target_id = int(parts[3])
        scope = None if is_sa else user_id
    elif action == 'all_users':
        target = 'all_users'
        scope = None
    elif action == 'all_chat_members':
        target = 'all_chat_members'
        scope = None
    elif action == 'chat_admins':
        target = 'chat_admins'
        scope = None if is_sa else user_id
    elif action == 'all':
        target = 'all'
        scope = user_id
    else:
        return await callback.answer("Unknown target", show_alert=True)

    await state.update_data(target=target, target_id=target_id, chat_scope_owner_id=scope)
    await state.set_state(BroadcastStates.composing_message)
    await callback.message.edit_text(
        "Send the message to broadcast (text, photo, video, document, or GIF):"
    )
    await callback.answer()


@router.message(BroadcastStates.enter_chat_id)
async def receive_chat_id(message: Message, state: FSMContext):
    try:
        cid = int((message.text or "").strip())
    except (TypeError, ValueError):
        return await message.answer("Please send a numeric chat ID.")

    data = await state.get_data()
    is_sa = data.get('is_super_admin_broadcast', False)
    await state.update_data(
        target='chat_members',
        target_id=cid,
        chat_scope_owner_id=None if is_sa else message.from_user.id,
    )
    await state.set_state(BroadcastStates.composing_message)
    await message.answer("Now send the broadcast message (text, photo, video, document, or GIF):")


@router.message(BroadcastStates.composing_message)
async def receive_broadcast_message(
    message: Message,
    state: FSMContext,
    join_request_repo,
    chat_repo,
    user_repo,
):
    payload = build_broadcast_payload(message)
    if not payload:
        return await message.answer(
            "Unsupported message type. Send text, photo, video, GIF, or document."
        )

    await state.update_data(payload=payload)

    data = await state.get_data()
    target = data.get('target')
    target_id = data.get('target_id')
    scope = data.get('chat_scope_owner_id')

    estimate = await estimate_recipients(
        target,
        chat_scope_owner_id=scope,
        target_id=target_id,
        user_repo=user_repo,
        chat_repo=chat_repo,
        join_request_repo=join_request_repo,
    )

    await state.update_data(estimate=estimate)
    await state.set_state(BroadcastStates.confirming)

    job_id = str(uuid.uuid4())
    await state.update_data(job_id=job_id)

    label = TARGET_LABELS.get(target, target)
    if target_id:
        label = f"{label} ({target_id})"
    text = (
        f"📊 <b>Broadcast Summary</b>\n\n"
        f"Target: {label}\n"
        f"Estimated recipients: <b>{estimate}</b>\n\n"
        "Start sending?"
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
    scope = data.get('chat_scope_owner_id')

    await broadcast_repo.create_job({
        '_id': job_id,
        'owner_id': callback.from_user.id,
        'target': target,
        'target_id': target_id,
        'chat_scope_owner_id': scope,
        'web_created': False,
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
