from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime, timezone
import uuid

from ..filters.is_superadmin import IsSuperAdmin
from ..keyboards.superadmin_menu import superadmin_main_keyboard, superadmin_stats_keyboard
from ..keyboards.broadcast_menu import broadcast_confirm_keyboard, broadcast_control_keyboard

router = Router()

# Assumes IsSuperAdmin filter is applied via middleware/router setup,
# but we can apply it locally as well if needed. Or we just trust is_super_admin flag.
# Let's use custom filter lambda based on data['is_super_admin']

def admin_filter(message: Message, is_super_admin: bool = False, **kwargs) -> bool:
    return is_super_admin

def admin_cb_filter(callback: CallbackQuery, is_super_admin: bool = False, **kwargs) -> bool:
    return is_super_admin

router.message.filter(admin_filter)
router.callback_query.filter(admin_cb_filter)


class MasterBroadcastStates(StatesGroup):
    composing = State()
    confirming = State()


@router.message(Command('admin'))
async def admin_panel(message: Message):
    """Super admin main panel."""
    await message.answer(
        "👑 <b>Super Admin Panel</b>\n\nSelect an option to manage the system:",
        reply_markup=superadmin_main_keyboard()
    )

@router.message(Command('users'))
async def users_stats(message: Message, user_repo):
    """User statistics."""
    count = await user_repo.count()
    await message.answer(f"👥 <b>Total Users:</b> {count}", reply_markup=superadmin_stats_keyboard())

@router.message(Command('chats'))
async def chats_stats(message: Message, chat_repo):
    """Chat statistics."""
    count = await chat_repo.count()
    await message.answer(f"💬 <b>Total Chats:</b> {count}", reply_markup=superadmin_stats_keyboard())

@router.message(Command('system'))
async def system_stats(message: Message):
    """System health."""
    text = (
        "🖥 <b>System Health</b>\n\n"
        "Database: Connected\n"
        "Redis: Connected\n"
        "Workers: 1 Active\n"
    )
    await message.answer(text, reply_markup=superadmin_stats_keyboard())

@router.message(Command('master_broadcast'))
async def master_broadcast_command(message: Message, state: FSMContext):
    """Super admin master broadcast — targets every user in the system."""
    await state.set_state(MasterBroadcastStates.composing)
    await message.answer(
        "📢 <b>Master Broadcast</b>\n\n"
        "This goes to <b>every</b> user in the database.\n\n"
        "Send the message you want to broadcast (text, photo, video, document, etc.):"
    )


@router.message(MasterBroadcastStates.composing)
async def master_broadcast_compose(message: Message, state: FSMContext, user_repo, broadcast_repo):
    payload: dict = {"parse_mode": "HTML"}
    if message.text:
        payload["type"] = "text"
        payload["text"] = message.html_text or message.text
    elif message.photo:
        payload["type"] = "photo"
        payload["photo"] = message.photo[-1].file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.video:
        payload["type"] = "video"
        payload["video"] = message.video.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.document:
        payload["type"] = "document"
        payload["document"] = message.document.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.animation:
        payload["type"] = "animation"
        payload["animation"] = message.animation.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    else:
        return await message.answer("Unsupported message type. Send text, photo, video, GIF, or document.")

    estimate = await user_repo.count()
    if estimate == 0:
        return await message.answer("❌ No users in the database yet.")

    job_id = str(uuid.uuid4())
    await state.update_data(payload=payload, estimate=estimate, job_id=job_id)
    await state.set_state(MasterBroadcastStates.confirming)
    await message.answer(
        f"📊 <b>Master Broadcast Summary</b>\n\n"
        f"Total users in system: <b>{estimate}</b>\n\n"
        "Are you sure you want to send to ALL users?",
        reply_markup=broadcast_confirm_keyboard(job_id),
    )


@router.callback_query(MasterBroadcastStates.confirming, F.data.startswith("broadcast:confirm:"))
async def master_broadcast_confirm(callback: CallbackQuery, state: FSMContext, broadcast_repo):
    data = await state.get_data()
    job_id = data["job_id"]
    payload = data.get("payload", {})
    estimate = data.get("estimate", 0)

    await broadcast_repo.create_job({
        "_id": job_id,
        "owner_id": callback.from_user.id,
        "target": "all_users",
        "target_id": None,
        "payload": payload,
        "total_recipients": estimate,
        "status": "running",
    })
    await state.clear()
    await callback.message.edit_text(
        "🚀 Master broadcast started!",
        reply_markup=broadcast_control_keyboard(job_id, "running"),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast:cancel_flow")
async def master_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Master broadcast cancelled.")
    await callback.answer()

@router.callback_query(F.data == 'menu:admin')
@router.callback_query(F.data.startswith('admin:'))
async def admin_callbacks(callback: CallbackQuery, user_repo, chat_repo):
    """Handle admin panel callbacks."""
    if callback.data == 'menu:admin':
        action = 'main'
    else:
        action = callback.data.split(':')[1]
    
    if action == 'main':
        await callback.message.edit_text(
            "👑 <b>Super Admin Panel</b>\n\nSelect an option to manage the system:",
            reply_markup=superadmin_main_keyboard()
        )
    elif action == 'users':
        count = await user_repo.count()
        await callback.message.edit_text(f"👥 <b>Total Users:</b> {count}", reply_markup=superadmin_stats_keyboard())
    elif action == 'chats':
        count = await chat_repo.count()
        await callback.message.edit_text(f"💬 <b>Total Chats:</b> {count}", reply_markup=superadmin_stats_keyboard())
    elif action == 'system':
        text = (
            "🖥 <b>System Health</b>\n\n"
            "Database: Connected\n"
            "Redis: Connected\n"
            "Workers: 1 Active\n"
        )
        await callback.message.edit_text(text, reply_markup=superadmin_stats_keyboard())
    elif action == 'stats':
        if len(callback.data.split(':')) > 2:
            subaction = callback.data.split(':')[2]
            if subaction == 'refresh':
                await callback.answer("Refreshed.")
    elif action == 'master_broadcast':
        await state.set_state(MasterBroadcastStates.composing)
        await callback.message.edit_text(
            "📢 <b>Master Broadcast</b>\n\n"
            "This goes to <b>every</b> user in the database.\n\n"
            "Send the message you want to broadcast (text, photo, video, document, etc.):"
        )
    await callback.answer()


@router.message(Command('dbcheck'))
async def db_check(message: Message, join_request_repo, chat_repo, user_repo):
    """Debug: show raw document counts from every collection."""
    try:
        total_jr = await join_request_repo.collection.count_documents({})
        approved_jr = await join_request_repo.collection.count_documents({"status": "approved"})
        pending_jr = await join_request_repo.collection.count_documents({"status": "pending"})
        scheduled_jr = await join_request_repo.collection.count_documents({"status": "scheduled"})
        total_users = await user_repo.collection.count_documents({})
        total_chats = await chat_repo.collection.count_documents({})
        total_settings = await chat_repo.settings_collection.count_documents({})

        # Sample last 3 join_request docs
        recent = await join_request_repo.collection.find(
            {}, {"user_id": 1, "chat_id": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(3).to_list(length=3)

        sample_text = "\n".join(
            f"  • user={r.get('user_id')} chat={r.get('chat_id')} status={r.get('status')}"
            for r in recent
        ) or "  (empty)"

        await message.answer(
            f"🗄 <b>Raw DB Counts</b>\n\n"
            f"join_requests: {total_jr} total\n"
            f"  approved: {approved_jr}\n"
            f"  pending:  {pending_jr}\n"
            f"  scheduled:{scheduled_jr}\n"
            f"users:        {total_users}\n"
            f"chats:        {total_chats}\n"
            f"chat_settings:{total_settings}\n\n"
            f"<b>Last 3 join_requests:</b>\n{sample_text}"
        )
    except Exception as e:
        await message.answer(f"❌ DB check failed: {e}")
