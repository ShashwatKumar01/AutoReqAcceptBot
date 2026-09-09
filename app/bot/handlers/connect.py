"""
Manual connect / disconnect by chat_id, and chat-info on forward.

Commands:
  /connect <chat_id>      — register a chat the user owns, by its numeric id
  /disconnect <chat_id>   — mark a chat as disconnected

Reply on forward:
  When a user forwards a message from any chat (channel, group, supergroup),
  the bot replies with the chat's details: id, title, type, member count,
  and — if it is in our database — its current connection status.

This is a power-user flow for cases where the bot is added as admin but
the `my_chat_member` event isn't delivered, or the user wants to manage
chats by ID directly.
"""
import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from app.core.logging import get_logger

router = Router()
logger = get_logger('connect')


def _parse_chat_id(text: str) -> int | None:
    """Extract the first integer (with optional leading '-') from text."""
    m = re.search(r"-?\d{6,}", text or "")
    return int(m.group(0)) if m else None


def _format_chat_info(chat: dict) -> str:
    """Format a single chat's details for display."""
    chat_id = chat.get("chat_id", "?")
    title = chat.get("title") or "(no title)"
    ctype = chat.get("type") or "?"
    status = chat.get("status") or "?"
    admin_id = chat.get("admin_id")
    welcome_enabled = chat.get("welcome_enabled", "—")
    goodbye_enabled = chat.get("goodbye_enabled", "—")
    total_reqs = chat.get("total_join_requests", 0)
    total_approved = chat.get("total_approved", 0)
    return (
        f"💬 <b>{title}</b>\n"
        f"   <b>chat_id:</b> <code>{chat_id}</code>\n"
        f"   <b>type:</b> {ctype}\n"
        f"   <b>status:</b> {status}\n"
        f"   <b>admin_id:</b> {admin_id or '—'}\n"
        f"   <b>welcome:</b> {welcome_enabled}\n"
        f"   <b>goodbye:</b> {goodbye_enabled}\n"
        f"   <b>total requests:</b> {total_reqs} • <b>approved:</b> {total_approved}"
    )


@router.message(Command("connect"))
async def connect_command(message: Message, chat_repo, bot: Bot):
    """
    /connect <chat_id>

    Manually register a chat the user owns. Verifies the bot is a member of
    the chat (or at least can resolve it via getChat) before saving.
    """
    user_id = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        # Show usage + currently connected chats so user can pick one
        chats = await chat_repo.get_by_admin(user_id)
        if chats:
            listing = "\n".join(
                f"• <b>{c.get('title', '?')}</b> — <code>{c.get('chat_id')}</code>"
                for c in chats
            )
            await message.answer(
                "ℹ️ <b>Usage:</b> <code>/connect &lt;chat_id&gt;</code>\n\n"
                f"<b>Your connected chats:</b>\n{listing}\n\n"
                "Or forward a message from the chat and I'll show its details."
            )
        else:
            await message.answer(
                "ℹ️ <b>Usage:</b> <code>/connect &lt;chat_id&gt;</code>\n\n"
                "Or forward a message from the chat to see its details."
            )
        return

    target_id = _parse_chat_id(args[1])
    if target_id is None:
        return await message.answer("❌ Couldn't parse a chat id. Send `/connect 1234567890`.")

    # Verify the bot can see the chat
    try:
        tg_chat = await bot.get_chat(target_id)
    except Exception as e:
        return await message.answer(
            f"❌ Couldn't load chat <code>{target_id}</code>.\n\n"
            f"<code>{type(e).__name__}: {str(e)[:150]}</code>\n\n"
            "Make sure:\n"
            "• the chat id is correct\n"
            "• the bot has been added to that chat as admin"
        )

    title = tg_chat.title or tg_chat.full_name or "(no title)"
    ctype = tg_chat.type.value if hasattr(tg_chat.type, "value") else str(tg_chat.type)

    # Verify the requesting user is the chat owner / creator (best effort —
    # getChat doesn't expose members without explicit calls)
    try:
        member = await bot.get_chat_member(target_id, user_id)
        user_is_owner = member.status in ("creator", "administrator")
    except Exception:
        user_is_owner = False

    chat_data = {
        "chat_id": target_id,
        "title": title,
        "type": ctype,
        "admin_id": user_id,
        "status": "connected",
        "manually_connected": True,
    }
    await chat_repo.upsert(chat_data)
    await chat_repo.upsert_admin(target_id, user_id)

    warning = ""
    if not user_is_owner:
        warning = (
            "\n\n⚠️ <i>I couldn't confirm you're an admin of this chat — "
            "make sure the bot was actually added there as admin.</i>"
        )

    await message.answer(
        f"✅ <b>Connected!</b>\n\n"
        f"{_format_chat_info(await chat_repo.get(target_id))}{warning}"
    )
    logger.info("manual connect", chat_id=target_id, user_id=user_id, title=title)


@router.message(Command("disconnect"))
async def disconnect_command(message: Message, chat_repo):
    """
    /disconnect <chat_id>
    Marks the chat as disconnected. Does not kick the bot — just removes
    it from the user's active list.
    """
    user_id = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        return await message.answer(
            "ℹ️ <b>Usage:</b> <code>/disconnect &lt;chat_id&gt;</code>"
        )

    target_id = _parse_chat_id(args[1])
    if target_id is None:
        return await message.answer("❌ Couldn't parse a chat id. Send `/disconnect 1234567890`.")

    chat = await chat_repo.get(target_id)
    if not chat:
        return await message.answer(
            f"❌ Chat <code>{target_id}</code> is not registered with this bot."
        )

    if chat.get("admin_id") and chat["admin_id"] != user_id:
        # Not the original admin — only allow if user is super admin (handled by
        # the auth middleware later, but be explicit here).
        from app.core.config import get_settings
        if user_id not in (get_settings().super_admin_id_list or []):
            return await message.answer(
                "⛔ Only the admin who connected this chat (or a super admin) "
                "can disconnect it."
            )

    await chat_repo.update_status(target_id, "disconnected")
    await message.answer(f"✅ Disconnected <b>{chat.get('title', target_id)}</b>.")
    logger.info("manual disconnect", chat_id=target_id, user_id=user_id)


# ──────────────────────────────────────────────────────────────────────────────
# Forwarded-message handler — show chat details when user forwards anything
# ──────────────────────────────────────────────────────────────────────────────

@router.message(F.forward_from_chat)
async def forwarded_message_info(message: Message, chat_repo):
    """
    When a user forwards a message from any chat, reply with the chat's
    connection status. Works in private chat only.
    """
    if message.chat.type != ChatType.PRIVATE:
        return

    fwd = message.forward_from_chat
    if not fwd:
        return

    target_id = fwd.id
    title = fwd.title or fwd.full_name or "(no title)"
    ctype = fwd.type.value if hasattr(fwd.type, "value") else str(fwd.type)

    # Check if it's already in our DB
    chat = await chat_repo.get(target_id)

    if chat:
        info = _format_chat_info(chat)
        if chat.get("status") == "disconnected":
            info += (
                "\n\n<b>Commands:</b>\n"
                f"<code>/connect {target_id}</code> — reconnect\n"
                f"<code>/disconnect {target_id}</code> — keep disconnected"
            )
    else:
        info = (
            f"💬 <b>{title}</b>\n"
            f"   <b>chat_id:</b> <code>{target_id}</code>\n"
            f"   <b>type:</b> {ctype}\n"
            f"   <b>status:</b> not connected\n\n"
            f"<b>To connect:</b> <code>/connect {target_id}</code>\n\n"
            "<i>(Note: the bot must be an admin in that chat for the "
            "connect to work.)</i>"
        )

    await message.answer(info)
    logger.info("forward info shown", chat_id=target_id, user_id=message.from_user.id)
