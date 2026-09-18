"""Super-admin approve / reject chat-owner broadcasts."""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.core.config import get_settings
from app.services.broadcast_approval import approve_broadcast, reject_broadcast
from ..keyboards.broadcast_menu import broadcast_approve_skip_keyboard

router = Router()


class BroadcastModStates(StatesGroup):
    waiting_reject_remark = State()
    waiting_approve_remark = State()


def _admin_filter(callback: CallbackQuery, is_super_admin: bool = False, **kwargs) -> bool:
    return is_super_admin


router.callback_query.filter(_admin_filter)


@router.callback_query(F.data.startswith("broadcast:mod:approve:"))
async def mod_approve_prompt(callback: CallbackQuery, state: FSMContext, broadcast_repo):
    job_id = callback.data.split(":")[3]
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("approval_status") != "pending":
        return await callback.answer("Already handled or not found.", show_alert=True)
    await state.set_state(BroadcastModStates.waiting_approve_remark)
    await state.update_data(mod_job_id=job_id)
    await callback.message.answer(
        "✅ <b>Approve broadcast</b>\n\n"
        "Send an optional note for the chat owner, or tap the button below.",
        parse_mode="HTML",
        reply_markup=broadcast_approve_skip_keyboard(job_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:mod:approve_skip:"))
async def mod_approve_skip(callback: CallbackQuery, state: FSMContext, broadcast_repo):
    job_id = callback.data.split(":")[3]
    await state.clear()
    job = await approve_broadcast(
        callback.bot, get_settings(), broadcast_repo, job_id, callback.from_user.id, None,
    )
    if not job:
        return await callback.answer("Could not approve.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Approved — sending started.")
    await callback.message.answer("✅ Broadcast approved and running.")


@router.callback_query(F.data.startswith("broadcast:mod:reject:"))
async def mod_reject_prompt(callback: CallbackQuery, state: FSMContext, broadcast_repo):
    job_id = callback.data.split(":")[3]
    job = await broadcast_repo.get_job(job_id)
    if not job or job.get("approval_status") != "pending":
        return await callback.answer("Already handled or not found.", show_alert=True)
    await state.set_state(BroadcastModStates.waiting_reject_remark)
    await state.update_data(mod_job_id=job_id)
    await callback.message.answer(
        "❌ <b>Reject broadcast</b>\n\n"
        "Send the <b>remark</b> message for the chat owner (required).",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:mod:cancel:"))
async def mod_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled.")


@router.message(BroadcastModStates.waiting_approve_remark)
async def mod_approve_remark(message: Message, state: FSMContext, broadcast_repo):
    if message.text and message.text.strip().startswith("/"):
        if message.text.strip() == "/cancel":
            await state.clear()
            return await message.answer("Cancelled.")
        return
    data = await state.get_data()
    job_id = data.get("mod_job_id")
    remark = message.html_text or message.text or ""
    await state.clear()
    job = await approve_broadcast(
        message.bot, get_settings(), broadcast_repo, job_id, message.from_user.id, remark,
    )
    if job:
        await message.answer("✅ Broadcast approved and running.")
    else:
        await message.answer("Could not approve (already handled?).")


@router.message(BroadcastModStates.waiting_reject_remark)
async def mod_reject_remark(message: Message, state: FSMContext, broadcast_repo):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        return await message.answer("Cancelled.")
    remark = (message.html_text or message.text or "").strip()
    if not remark:
        return await message.answer("Please send a rejection remark.")
    data = await state.get_data()
    job_id = data.get("mod_job_id")
    await state.clear()
    job = await reject_broadcast(
        message.bot, get_settings(), broadcast_repo, job_id, message.from_user.id, remark,
    )
    if job:
        await message.answer("⛔ Broadcast rejected; owner notified.")
    else:
        await message.answer("Could not reject (already handled?).")
