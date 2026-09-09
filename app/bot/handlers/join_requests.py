from datetime import datetime, timedelta, timezone

from aiogram import Router, Bot, F
from aiogram.types import ChatJoinRequest, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.logging import get_logger

router = Router()
logger = get_logger('join_requests')


@router.chat_join_request()
async def handle_join_request(
    event: ChatJoinRequest,
    bot: Bot,
    join_request_repo,
    chat_repo,
    user_repo,
    welcome_service,
):
    """
    Main join request handler.

    - Captcha ON: DM verification button; approve only after click.
    - Auto approval OFF: store as pending (manual approval).
    - Auto approval ON + delay: schedule for approval worker.
    - Auto approval ON + no delay: approve immediately.
    - Welcome messages handled via WelcomeService (on_request / on_approval / delayed).
    """
    user_id = event.from_user.id
    chat_id = event.chat.id
    from_user = event.from_user

    logger.info("chat_join_request received",
                chat_id=chat_id, user_id=user_id,
                username=from_user.username,
                chat_title=event.chat.title)

    approval = await chat_repo.get_approval_settings(chat_id)
    captcha_enabled = approval["captcha_enabled"]
    auto_approve = approval["enabled"]
    delay_seconds = approval["delay"]

    request_doc = await join_request_repo.create({
        "user_id": user_id,
        "chat_id": chat_id,
        "first_name": from_user.first_name or "",
        "last_name": from_user.last_name or "",
        "username": from_user.username or "",
        "status": "pending",
        "captcha_required": captcha_enabled,
    })

    # Welcome on request (before approval)
    await welcome_service.handle_join_request(
        user_id=user_id,
        chat_id=chat_id,
        from_user=from_user,
        request_doc=request_doc,
    )

    if captcha_enabled:
        try:
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ I'm not a robot",
                callback_data=f"captcha:verify:{chat_id}:{user_id}",
            )
            chat_title = event.chat.title or "the group"
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"Hello <b>{from_user.first_name or ''}</b>,\n\n"
                    f"To join <b>{chat_title}</b> confirm that you are not a robot "
                    f"by tapping the button below. ⬇️"
                ),
                reply_markup=builder.as_markup(),
            )
        except Exception as e:
            logger.warning("Captcha DM failed, falling back to auto-approve",
                           chat_id=chat_id, user_id=user_id, error=str(e))
            if auto_approve:
                await _approve_and_track(
                    bot=bot,
                    join_request_repo=join_request_repo,
                    user_repo=user_repo,
                    chat_repo=chat_repo,
                    welcome_svc=welcome_service,
                    from_user=from_user,
                    chat_id=chat_id,
                    user_id=user_id,
                    request_doc=request_doc,
                )
        return

    if not auto_approve:
        logger.info("Auto approval disabled — request left pending",
                    chat_id=chat_id, user_id=user_id)
        return

    if delay_seconds > 0:
        schedule_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        await join_request_repo.update(
            {"user_id": user_id, "chat_id": chat_id},
            {"status": "scheduled", "scheduled_at": schedule_at},
        )
        logger.info("Join request scheduled for delayed approval",
                    chat_id=chat_id, user_id=user_id, delay=delay_seconds)
        return

    await _approve_and_track(
        bot=bot,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
        chat_repo=chat_repo,
        welcome_svc=welcome_service,
        from_user=from_user,
        chat_id=chat_id,
        user_id=user_id,
        request_doc=request_doc,
    )


async def _approve_and_track(
    bot: Bot,
    join_request_repo,
    user_repo,
    chat_repo,
    welcome_svc,
    from_user,
    chat_id: int,
    user_id: int,
    request_doc: dict | None = None,
) -> None:
    """Approve a join request, upsert the user, send welcome message."""
    try:
        await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        logger.info("Telegram approved join request",
                    chat_id=chat_id, user_id=user_id)
    except Exception as e:
        logger.error("approve_chat_join_request failed",
                     chat_id=chat_id, user_id=user_id, error=str(e),
                     exc_info=True)
        try:
            chat_obj = await chat_repo.collection.find_one({"chat_id": chat_id})
            owner_id = (chat_obj or {}).get("admin_id")
            if owner_id:
                await bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"⚠️ <b>Auto-approval failed</b> for "
                        f"<b>{(from_user.first_name or 'user')}</b> in "
                        f"<b>{(chat_obj or {}).get('title', 'a chat')}</b>.\n\n"
                        f"<code>{type(e).__name__}: {str(e)[:200]}</code>\n\n"
                        "Make sure the bot has the <b>Add Members</b> / "
                        "<b>Add Subscribers</b> permission."
                    ),
                )
        except Exception:
            pass
        return

    await join_request_repo.update(
        {"user_id": user_id, "chat_id": chat_id},
        {"status": "approved"},
    )

    try:
        await user_repo.upsert({
            "telegram_id": from_user.id,
            "username": from_user.username,
            "first_name": from_user.first_name,
            "last_name": from_user.last_name,
            "language_code": getattr(from_user, "language_code", None),
            "is_bot": False,
            "is_active": True,
            "chat_id": chat_id,
        })
        await chat_repo.increment_counter(chat_id, "total_join_requests")
        await chat_repo.increment_counter(chat_id, "total_approved")
    except Exception as e:
        logger.error("User upsert/counter failed", chat_id=chat_id,
                     user_id=user_id, error=str(e))

    try:
        await welcome_svc.handle_approval(
            user_id=user_id,
            chat_id=chat_id,
            from_user=from_user,
            request_doc=request_doc,
        )
    except Exception as e:
        logger.error("Welcome dispatch error", user_id=user_id, chat_id=chat_id, error=str(e))

    logger.info("Join request approved + user tracked",
                chat_id=chat_id, user_id=user_id,
                username=from_user.username)


@router.callback_query(lambda c: c.data and c.data.startswith("captcha:verify:"))
async def captcha_verify_callback(
    callback: CallbackQuery,
    bot: Bot,
    join_request_repo,
    user_repo,
    chat_repo,
    welcome_service,
):
    """User clicked 'I'm not a robot' — approve the pending join request."""
    parts = callback.data.split(":")
    if len(parts) < 4:
        return await callback.answer("Invalid request.", show_alert=True)
    try:
        chat_id = int(parts[2])
        user_id = int(parts[3])
    except (TypeError, ValueError):
        return await callback.answer("Invalid request.", show_alert=True)

    if callback.from_user.id != user_id:
        return await callback.answer("This isn't your captcha.", show_alert=True)

    await _approve_and_track(
        bot=bot,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
        chat_repo=chat_repo,
        welcome_svc=welcome_service,
        from_user=callback.from_user,
        chat_id=chat_id,
        user_id=user_id,
    )

    try:
        await callback.message.edit_text("✅ Verified! You are approved. 🎉")
    except Exception:
        pass
    await callback.answer("Approved!")
