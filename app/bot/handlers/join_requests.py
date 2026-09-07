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
):
    """
    Main join request handler.

    Two modes (driven by chat_settings.captcha_enabled):
    - Captcha OFF (default): record + approve immediately via Telegram API.
    - Captcha ON: DM the user an "I'm not a robot" button. Approval only
      happens when they click it.

    On every approval we upsert the user into `users` so they appear in
    /stats and /broadcast. Welcome message is sent by the approval flow
    via WelcomeService (wired in the worker / approval service).
    """
    user_id = event.from_user.id
    chat_id = event.chat.id
    from_user = event.from_user

    # Look up chat settings to decide mode
    settings = await chat_repo.get_chat_settings_with_defaults(chat_id)
    captcha_enabled = bool(settings.get("captcha_enabled", False))

    # Persist the request (idempotent)
    request_doc = await join_request_repo.create({
        "user_id": user_id,
        "chat_id": chat_id,
        "first_name": from_user.first_name or "",
        "last_name": from_user.last_name or "",
        "username": from_user.username or "",
        "status": "pending",
        "captcha_required": captcha_enabled,
    })

    # ── On-request welcome (before approval) ──────────────────────────────────
    # We call welcome_service via bot's data dict if available; if not wired,
    # the welcome will still fire via approval flow.
    # The join_requests handler is thin — it only approves; welcome timing
    # is controlled by WelcomeService based on chat_settings.welcome_trigger.

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
            await _approve_and_track(
                bot=bot,
                join_request_repo=join_request_repo,
                user_repo=user_repo,
                chat_repo=chat_repo,
                from_user=from_user,
                chat_id=chat_id,
                user_id=user_id,
                request_doc=request_doc,
            )
        return

    # Captcha OFF: approve immediately
    await _approve_and_track(
        bot=bot,
        join_request_repo=join_request_repo,
        user_repo=user_repo,
        chat_repo=chat_repo,
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
    from_user,
    chat_id: int,
    user_id: int,
    request_doc: dict | None = None,
) -> None:
    """
    Approve a join request, upsert the user, send welcome message.
    """
    try:
        await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
    except Exception as e:
        logger.error("approve_chat_join_request failed",
                     chat_id=chat_id, user_id=user_id, error=str(e))
        return

    await join_request_repo.update(
        {"user_id": user_id, "chat_id": chat_id},
        {"status": "approved"},
    )

    # Upsert user so they appear in stats + broadcast
    try:
        await user_repo.upsert({
            "telegram_id": from_user.id,
            "username": from_user.username,
            "first_name": from_user.first_name,
            "last_name": from_user.last_name,
            "language_code": getattr(from_user, "language_code", None),
            "is_bot": False,
            "is_active": True,
            "chat_id": chat_id,  # added to chat_ids via $addToSet
        })
        # Increment chat counters
        await chat_repo.increment_counter(chat_id, "total_join_requests")
        await chat_repo.increment_counter(chat_id, "total_approved")
    except Exception as e:
        logger.error("User upsert/counter failed", chat_id=chat_id,
                     user_id=user_id, error=str(e))

    # ── Welcome message ───────────────────────────────────────────────────────
    # Load settings and decide based on trigger
    try:
        ws_settings = await chat_repo.get_chat_settings_with_defaults(chat_id)
        welcome_enabled = ws_settings.get("welcome_enabled", True)
        welcome_trigger = ws_settings.get("welcome_trigger", "on_approval")
        welcome_delay = ws_settings.get("welcome_delay_seconds", 0)
        welcome_text = ws_settings.get("welcome_text", "")
        welcome_media_id = ws_settings.get("welcome_media_file_id", "")
        welcome_media_type = ws_settings.get("welcome_media_type", "photo")
        welcome_buttons = ws_settings.get("welcome_buttons", [])

        if welcome_enabled and welcome_trigger == "on_approval" and (welcome_text or welcome_media_id):
            # Build keyboard from buttons
            markup = None
            if welcome_buttons:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                rows: dict[int, list] = {}
                for btn in welcome_buttons:
                    row_idx = int(btn.get("row", 1))
                    rows.setdefault(row_idx, []).append(
                        InlineKeyboardButton(text=btn["text"][:64], url=btn.get("url"))
                    )
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[rows[i] for i in sorted(rows)]
                )

            chat_doc = await chat_repo.get(chat_id) or {}
            # Substitute variables
            first = from_user.first_name or ""
            last = from_user.last_name or ""
            uname = from_user.username or ""
            uid = str(from_user.id)
            chat_title = chat_doc.get("title", "our group")
            text = (
                welcome_text
                .replace("{first_name}", first)
                .replace("{last_name}", last)
                .replace("{username}", f"@{uname}" if uname else first)
                .replace("{user_id}", uid)
                .replace("{chat_title}", chat_title)
            ) if welcome_text else ""

            try:
                if welcome_media_id and welcome_media_type == "photo":
                    await bot.send_photo(
                        chat_id=user_id, photo=welcome_media_id,
                        caption=text[:1024] or None, parse_mode="HTML",
                        reply_markup=markup,
                    )
                elif welcome_media_id and welcome_media_type == "video":
                    await bot.send_video(
                        chat_id=user_id, video=welcome_media_id,
                        caption=text[:1024] or None, parse_mode="HTML",
                        reply_markup=markup,
                    )
                elif welcome_media_id and welcome_media_type == "animation":
                    await bot.send_animation(
                        chat_id=user_id, animation=welcome_media_id,
                        caption=text[:1024] or None, parse_mode="HTML",
                        reply_markup=markup,
                    )
                elif welcome_media_id and welcome_media_type == "document":
                    await bot.send_document(
                        chat_id=user_id, document=welcome_media_id,
                        caption=text[:1024] or None, parse_mode="HTML",
                        reply_markup=markup,
                    )
                elif text:
                    await bot.send_message(
                        chat_id=user_id, text=text[:4096],
                        parse_mode="HTML", reply_markup=markup,
                    )

                await join_request_repo.update(
                    {"user_id": user_id, "chat_id": chat_id},
                    {"welcome_status": "sent"},
                )
                await chat_repo.increment_counter(chat_id, "total_welcome_sent")
                logger.info("Welcome sent on_approval", user_id=user_id, chat_id=chat_id)

            except Exception as e:
                logger.warning("Welcome send failed", user_id=user_id, chat_id=chat_id, error=str(e))
                await join_request_repo.update(
                    {"user_id": user_id, "chat_id": chat_id},
                    {"welcome_status": "failed"},
                )

        elif welcome_enabled and welcome_trigger == "delayed" and welcome_delay > 0:
            # Schedule welcome for later
            from datetime import datetime, timedelta, timezone
            schedule_at = datetime.now(timezone.utc) + timedelta(seconds=welcome_delay)
            await join_request_repo.update(
                {"user_id": user_id, "chat_id": chat_id},
                {"welcome_status": "scheduled", "welcome_scheduled_for": schedule_at},
            )
            logger.info("Welcome scheduled", user_id=user_id, chat_id=chat_id, delay=welcome_delay)

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
        from_user=callback.from_user,
        chat_id=chat_id,
        user_id=user_id,
    )

    try:
        await callback.message.edit_text("✅ Verified! You are approved. 🎉")
    except Exception:
        pass
    await callback.answer("Approved!")
