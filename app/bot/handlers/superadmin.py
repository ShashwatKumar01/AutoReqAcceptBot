from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone

from app.core.config import get_settings
from app.web.services.system_health import check_system_health
from ..keyboards.superadmin_menu import superadmin_main_keyboard, superadmin_stats_keyboard
from ..handlers.broadcast import _start_broadcast_picker

router = Router()


def admin_filter(message: Message, is_super_admin: bool = False, **kwargs) -> bool:
    return is_super_admin

def admin_cb_filter(callback: CallbackQuery, is_super_admin: bool = False, **kwargs) -> bool:
    return is_super_admin

router.message.filter(admin_filter)
router.callback_query.filter(admin_cb_filter)


def _admin_url() -> str:
    return get_settings().admin_web_url


async def _format_system_health(db, redis_client) -> str:
    health = await check_system_health(db, redis_client)
    mongo = health["mongodb"]
    redis = health["redis"]
    uses = ", ".join(health.get("redis_used_for") or [])
    return (
        "🖥 <b>System Health</b>\n\n"
        f"<b>MongoDB:</b> {mongo}\n"
        f"<b>Redis:</b> {redis} <i>(in use if online)</i>\n"
        f"<b>Workers:</b> approval + broadcast in-process\n\n"
        f"<b>Redis roles:</b> {uses}\n\n"
        f"Web dashboard: <code>{_admin_url()}</code>"
    )


@router.message(Command('admin'))
async def admin_panel(message: Message):
    await message.answer(
        "👑 <b>Super Admin Panel</b>\n\n"
        "Manage the bot from here or open the 🌐 <b>Web Dashboard</b> "
        "for full stats, search, filters, and broadcast progress.\n\n"
        f"Dashboard: <code>{_admin_url()}</code>",
        reply_markup=superadmin_main_keyboard(_admin_url()),
    )


@router.message(Command('users'))
async def users_stats(message: Message, user_repo):
    count = await user_repo.count()
    await message.answer(f"👥 <b>Total Users:</b> {count}", reply_markup=superadmin_stats_keyboard())


@router.message(Command('chats'))
async def chats_stats(message: Message, chat_repo):
    count = await chat_repo.count()
    await message.answer(f"💬 <b>Total Chats:</b> {count}", reply_markup=superadmin_stats_keyboard())


@router.message(Command('system'))
async def system_stats(message: Message, db, redis_client):
    text = await _format_system_health(db, redis_client)
    await message.answer(text, reply_markup=superadmin_stats_keyboard())


@router.message(Command('master_broadcast'))
async def master_broadcast_command(message: Message, state: FSMContext, chat_repo):
    await _start_broadcast_picker(message, state, chat_repo, message.from_user.id, True)


@router.callback_query(F.data == 'menu:admin')
@router.callback_query(F.data.startswith('admin:'))
async def admin_callbacks(callback: CallbackQuery, state: FSMContext, user_repo, chat_repo, db, redis_client):
    if callback.data == 'menu:admin':
        action = 'main'
    else:
        action = callback.data.split(':')[1]

    url = _admin_url()

    if action == 'main':
        await callback.message.edit_text(
            "👑 <b>Super Admin Panel</b>\n\n"
            "Use the web dashboard for search, filters, sort, and live broadcast progress.\n\n"
            f"URL: <code>{url}</code>",
            reply_markup=superadmin_main_keyboard(url),
        )
    elif action == 'users':
        count = await user_repo.count()
        await callback.message.edit_text(
            f"👥 <b>Total Users:</b> {count}\n\n"
            f"Full list: <code>{url}</code> → Users tab",
            reply_markup=superadmin_stats_keyboard(),
        )
    elif action == 'chats':
        count = await chat_repo.count()
        await callback.message.edit_text(
            f"💬 <b>Total Chats:</b> {count}\n\n"
            f"Full list: <code>{url}</code> → Chats tab",
            reply_markup=superadmin_stats_keyboard(),
        )
    elif action == 'requests':
        await callback.message.edit_text(
            "📨 <b>Join Requests</b>\n\n"
            "Browse, filter, and sort all join requests in the web dashboard.\n\n"
            f"Open: <code>{url}</code> → Join Requests tab",
            reply_markup=superadmin_stats_keyboard(),
        )
    elif action == 'broadcasts':
        await callback.message.edit_text(
            "📢 <b>Broadcasts</b>\n\n"
            "View live progress, pause, resume, or cancel jobs from the web dashboard.\n\n"
            f"Open: <code>{url}</code> → Broadcasts tab",
            reply_markup=superadmin_stats_keyboard(),
        )
    elif action == 'plans':
        await callback.message.edit_text(
            "💳 <b>Plans</b>\n\n"
            "Plan management is available via the bot /plan command for now.",
            reply_markup=superadmin_stats_keyboard(),
        )
    elif action == 'system':
        text = await _format_system_health(db, redis_client)
        await callback.message.edit_text(text, reply_markup=superadmin_stats_keyboard())
    elif action == 'stats':
        if len(callback.data.split(':')) > 2 and callback.data.split(':')[2] == 'refresh':
            await callback.answer("Refreshed.")
            return
    elif action == 'master_broadcast':
        await _start_broadcast_picker(callback, state, chat_repo, callback.from_user.id, True)
    await callback.answer()


@router.message(Command('dbcheck'))
async def db_check(message: Message, join_request_repo, chat_repo, user_repo, broadcast_repo):
    try:
        total_jr = await join_request_repo.collection.count_documents({})
        approved_jr = await join_request_repo.collection.count_documents({"status": "approved"})
        pending_jr = await join_request_repo.collection.count_documents({"status": "pending"})
        scheduled_jr = await join_request_repo.collection.count_documents({"status": "scheduled"})
        total_users = await user_repo.collection.count_documents({})
        total_chats = await chat_repo.collection.count_documents({})
        total_settings = await chat_repo.settings_collection.count_documents({})
        running_bc = await broadcast_repo.collection.count_documents({"status": "running"})

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
            f"chat_settings:{total_settings}\n"
            f"broadcasts running: {running_bc}\n\n"
            f"<b>Last 3 join_requests:</b>\n{sample_text}\n\n"
            f"Dashboard: <code>{_admin_url()}</code>"
        )
    except Exception as e:
        await message.answer(f"❌ DB check failed: {e}")
