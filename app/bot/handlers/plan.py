"""
Plan / subscription screen — shows the user's current plan and lists
upgrades with a callback. Payment is not wired up yet (paywall TODO).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


def _format_plan(p: dict, current: bool = False) -> str:
    if not p:
        return "—"
    name = p.get("name", p.get("plan_id", "—"))
    price = p.get("price", 0)
    bp = p.get("broadcasts_per_day", 0)
    mr = p.get("max_recipients", 0)
    mc = p.get("max_chats", 0)
    bp_s = "Unlimited" if bp == -1 else str(bp)
    mr_s = "Unlimited" if mr == -1 else (f"{mr:,}" if mr else "—")
    mc_s = "Unlimited" if mc == -1 else str(mc)
    price_s = f"${price:.2f}/mo" if price else "Free"
    icon = "✅ " if current else ""
    return (
        f"{icon}<b>{name}</b> — {price_s}\n"
        f"     Broadcasts/day: {bp_s} • Recipients: {mr_s} • Chats: {mc_s}"
    )


@router.message(Command("plan"))
async def plan_command(message: Message, subscription_repo):
    user_id = message.from_user.id
    sub = await subscription_repo.get_active_subscription(user_id)
    if not sub:
        sub = {"plan_id": "FREE", "status": "active",
               "expiry_date": None}
        await subscription_repo.upsert_subscription(user_id, sub)

    current_plan = await subscription_repo.get_plan(sub.get("plan_id", "FREE"))
    plans = await subscription_repo.get_all_plans()
    plans.sort(key=lambda p: p.get("price", 0) or 0)

    text = (
        f"💳 <b>Your Plan</b>\n\n"
        + _format_plan(current_plan, current=True)
        + f"\n\n<b>Available plans</b>:\n"
        + "\n".join(_format_plan(p) for p in plans)
        + "\n\n<i>Payment integration coming soon — for now, contact the admin to upgrade.</i>"
    )

    b = InlineKeyboardBuilder()
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)
    await message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data == "menu:plan")
async def plan_menu(callback: CallbackQuery, subscription_repo):
    user_id = callback.from_user.id
    sub = await subscription_repo.get_active_subscription(user_id)
    if not sub:
        sub = {"plan_id": "FREE", "status": "active",
               "expiry_date": None}
        await subscription_repo.upsert_subscription(user_id, sub)

    current_plan = await subscription_repo.get_plan(sub.get("plan_id", "FREE"))
    plans = await subscription_repo.get_all_plans()
    plans.sort(key=lambda p: p.get("price", 0) or 0)

    text = (
        f"💳 <b>Your Plan</b>\n\n"
        + _format_plan(current_plan, current=True)
        + f"\n\n<b>Available plans</b>:\n"
        + "\n".join(_format_plan(p) for p in plans)
        + "\n\n<i>Payment integration coming soon — contact admin to upgrade.</i>"
    )

    b = InlineKeyboardBuilder()
    b.button(text="← Back to Menu", callback_data="menu:main")
    b.adjust(1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()
