from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER

from app.core.logging import get_logger
from app.services.welcome_settings_seed import seed_welcome_settings_if_missing

router = Router()
logger = get_logger('chat_member')


@router.my_chat_member()
async def bot_chat_member_updated(
    event: ChatMemberUpdated,
    bot: Bot,
    chat_repo,
):
    """
    Handle bot's own chat member status changes.

    The `chats` collection is keyed by `chat_id` (not `id`) — see
    ChatRepository.upsert_chat. The previous version wrote `"id": chat.id`
    and then `upsert_chat` raised KeyError, silently breaking chat
    registration.
    """
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status
    chat = event.chat
    added_by = event.from_user

    if new_status in ('administrator', 'creator'):
        logger.info("my_chat_member: bot became admin",
                    chat_id=chat.id, chat_title=chat.title,
                    new_status=new_status, old_status=old_status,
                    added_by=added_by.id if added_by else None)
        try:
            chat_data = {
                "chat_id": chat.id,
                "title": chat.title,
                "type": chat.type,
                "admin_id": added_by.id if added_by else None,
                "status": "connected",
            }
            await chat_repo.upsert(chat_data)
            await seed_welcome_settings_if_missing(chat_repo, chat.id)
            logger.info("my_chat_member: chat upserted",
                        chat_id=chat.id, title=chat.title)
            # Also record the adder in chat_admins so get_by_admin(user_id)
            # returns this chat. Without this, /welcome shows "no chats".
            if added_by:
                try:
                    await chat_repo.upsert_admin(chat.id, added_by.id)
                    logger.info("my_chat_member: admin upserted",
                                chat_id=chat.id, user_id=added_by.id)
                except Exception as e:
                    logger.warning("Failed to upsert admin",
                                   chat_id=chat.id, user_id=added_by.id,
                                   error=str(e))
        except Exception as e:
            logger.error("Failed to upsert chat on my_chat_member",
                         chat_id=chat.id, error=str(e))
            return

        has_invite_perm = getattr(event.new_chat_member, "can_invite_users", False)

        if added_by:
            try:
                msg = (
                    f"✅ <b>Bot connected to {chat.title}!</b>\n\n"
                    f"Next steps:\n"
                    f"1️⃣ Enable Join Requests in your group/channel settings\n"
                    f"2️⃣ Open /settings to configure approval delay\n"
                    f"3️⃣ Set up your welcome message\n\n"
                )
                if not has_invite_perm:
                    msg += "⚠️ <b>Missing permission:</b> I need <code>can_invite_users</code> to approve join requests!"

                await bot.send_message(added_by.id, msg)
            except Exception as e:
                logger.warning("Could not DM admin after connect",
                               admin_id=added_by.id, error=str(e))

    elif new_status in ('left', 'kicked', 'restricted'):
        if old_status in ('administrator', 'creator', 'member'):
            try:
                await chat_repo.update_status(chat.id, "disconnected")
            except Exception as e:
                logger.warning("Failed to mark chat disconnected",
                               chat_id=chat.id, error=str(e))
