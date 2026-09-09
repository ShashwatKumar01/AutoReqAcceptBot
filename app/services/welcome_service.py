from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.database.repositories import JoinRequestRepository, ChatRepository
from app.services.telegram_service import TelegramService
from app.core.logging import get_logger
from app.core.utils import utcnow


class WelcomeService:
    def __init__(
        self,
        chat_repo: ChatRepository,
        telegram_service: TelegramService,
        join_request_repo: Optional[JoinRequestRepository] = None,
    ):
        self.chat_repo = chat_repo
        self.telegram_service = telegram_service
        self.join_request_repo = join_request_repo
        self.logger = get_logger("welcome_service")

    # ──────────────────────────────────────────────────────────────
    # Public API called by join_requests handler and approval worker
    # ──────────────────────────────────────────────────────────────

    async def handle_join_request(
        self,
        user_id: int,
        chat_id: int,
        from_user,
        request_doc: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called BEFORE approval (trigger = on_request).
        Only sends if welcome_trigger == 'on_request'.
        """
        ws = await self._load_settings(chat_id)
        if not ws.get("welcome_enabled", True):
            return
        if ws.get("welcome_trigger", "on_approval") != "on_request":
            return
        await self._send(user_id, chat_id, from_user, ws, request_doc)

    async def handle_approval(
        self,
        user_id: int,
        chat_id: int,
        from_user,
        request_doc: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called AFTER approval.
        - on_approval → send immediately
        - delayed → schedule for later (stored in join_request doc)
        - on_request → skip (already sent)
        """
        ws = await self._load_settings(chat_id)
        if not ws.get("welcome_enabled", True):
            return

        trigger = ws.get("welcome_trigger", "on_approval")
        delay = ws.get("welcome_delay_seconds", 0)

        if trigger == "on_request":
            # Already sent at request time
            return

        if trigger == "delayed" and delay > 0:
            # Schedule: mark the join_request doc with welcome_scheduled_for
            if self.join_request_repo and request_doc:
                schedule_time = utcnow() + timedelta(seconds=delay)
                await self.join_request_repo.update(
                    {"user_id": user_id, "chat_id": chat_id},
                    {
                        "welcome_status": "scheduled",
                        "welcome_scheduled_for": schedule_time,
                    },
                )
                self.logger.info(
                    "Welcome scheduled",
                    user_id=user_id,
                    chat_id=chat_id,
                    delay_seconds=delay,
                )
            return

        # on_approval → send immediately
        await self._send(user_id, chat_id, from_user, ws, request_doc)

    async def process_due_welcome_messages(self, now: datetime) -> int:
        """
        Worker-side: find scheduled welcomes whose time has come and send them.
        Called periodically by the approval worker.
        """
        if not self.join_request_repo:
            return 0

        due = await self.join_request_repo.find({
            "welcome_status": "scheduled",
            "welcome_scheduled_for": {"$lte": now},
        })

        count = 0
        for req in due:
            try:
                ws = await self._load_settings(req["chat_id"])
                if ws.get("welcome_enabled", True):
                    # Build a minimal from_user-like dict from stored data
                    pseudo_user = _DictUser(
                        id=req["user_id"],
                        first_name=req.get("first_name", ""),
                        last_name=req.get("last_name"),
                        username=req.get("username"),
                    )
                    ok = await self._send(
                        req["user_id"], req["chat_id"], pseudo_user, ws, req
                    )
                    if ok:
                        count += 1
            except Exception as e:
                self.logger.error(
                    "Failed to send due welcome",
                    user_id=req.get("user_id"),
                    chat_id=req.get("chat_id"),
                    error=str(e),
                )
        return count

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    async def _load_settings(self, chat_id: int) -> Dict[str, Any]:
        """Load welcome settings from chat_settings collection with defaults."""
        raw = await self.chat_repo.get_chat_settings(chat_id) or {}
        return {
            "welcome_enabled": raw.get("welcome_enabled", True),
            "welcome_trigger": raw.get("welcome_trigger", "on_approval"),
            "welcome_delay_seconds": raw.get("welcome_delay_seconds", 0),
            "welcome_text": raw.get("welcome_text", ""),
            "welcome_media_file_id": raw.get("welcome_media_file_id", ""),
            "welcome_media_type": raw.get("welcome_media_type", "photo"),
            "welcome_buttons": raw.get("welcome_buttons", []),
            "welcome_parse_mode": raw.get("welcome_parse_mode", "HTML"),
        }

    async def _send(
        self,
        user_id: int,
        chat_id: int,
        from_user,
        ws: Dict[str, Any],
        request_doc: Optional[Dict[str, Any]],
    ) -> bool:
        """Build and send the welcome message. Returns True on success."""
        chat_doc = await self.chat_repo.get(chat_id) or {}
        text = self._substitute(ws["welcome_text"], from_user, chat_doc)
        keyboard = self._build_keyboard(ws["welcome_buttons"])
        media_id = ws.get("welcome_media_file_id", "")
        media_type = ws.get("welcome_media_type", "photo")
        parse_mode = ws.get("welcome_parse_mode", "HTML")

        if not text and not media_id:
            self.logger.debug(
                "Welcome skipped — no text or media configured",
                chat_id=chat_id,
            )
            return False

        bot: Bot | None = getattr(self.telegram_service, "bot", None)
        ok = False

        try:
            if bot and media_id:
                if media_type == "photo":
                    msg = await bot.send_photo(
                        chat_id=user_id, photo=media_id,
                        caption=text[:1024] or None, parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
                elif media_type == "video":
                    msg = await bot.send_video(
                        chat_id=user_id, video=media_id,
                        caption=text[:1024] or None, parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
                elif media_type == "animation":
                    msg = await bot.send_animation(
                        chat_id=user_id, animation=media_id,
                        caption=text[:1024] or None, parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
                elif media_type == "document":
                    msg = await bot.send_document(
                        chat_id=user_id, document=media_id,
                        caption=text[:1024] or None, parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
                else:
                    msg = await bot.send_message(
                        chat_id=user_id, text=text[:4096],
                        parse_mode=parse_mode, reply_markup=keyboard,
                    )
                ok = msg is not None
            elif bot:
                msg = await bot.send_message(
                    chat_id=user_id, text=text[:4096],
                    parse_mode=parse_mode, reply_markup=keyboard,
                )
                ok = msg is not None
            else:
                ok = await self.telegram_service.send_message(
                    chat_id=user_id, text=text[:4096], reply_markup=keyboard,
                )
        except Exception as e:
            self.logger.warning(
                "Welcome send failed",
                user_id=user_id, chat_id=chat_id, error=str(e),
            )
            ok = False

        # Update join_request status
        if self.join_request_repo and request_doc:
            patch = {
                "welcome_status": "sent" if ok else "failed",
            }
            if ok:
                patch["welcome_sent_at"] = utcnow()
            try:
                await self.join_request_repo.update(
                    {"user_id": user_id, "chat_id": chat_id},
                    patch,
                )
            except Exception:
                pass

        # Increment counter on the chat doc
        if ok:
            try:
                await self.chat_repo.increment_counter(chat_id, "total_welcome_sent")
            except Exception:
                pass

        self.logger.info(
            "Welcome sent" if ok else "Welcome failed",
            user_id=user_id, chat_id=chat_id,
        )
        return ok

    @staticmethod
    def _substitute(template: str, from_user, chat_doc: Dict[str, Any]) -> str:
        """Replace {variables} in template. Handles missing keys safely."""
        if not template:
            return ""
        first = getattr(from_user, "first_name", "") or ""
        last = getattr(from_user, "last_name", "") or ""
        username = getattr(from_user, "username", "") or ""
        uid = str(getattr(from_user, "id", ""))
        chat_title = chat_doc.get("title", "our group")
        chat_uname = chat_doc.get("username", "")
        return (
            template
            .replace("{first_name}", first)
            .replace("{last_name}", last)
            .replace("{username}", f"@{username}" if username else first)
            .replace("{user_id}", uid)
            .replace("{chat_title}", chat_title)
            .replace("{chat_username}", f"@{chat_uname}" if chat_uname else chat_title)
        )

    @staticmethod
    def _build_keyboard(buttons: List[Dict[str, Any]]) -> Optional[InlineKeyboardMarkup]:
        if not buttons:
            return None
        rows: dict[int, list] = {}
        for btn in buttons:
            row_idx = int(btn.get("row", 1))
            kwargs = {"text": str(btn["text"])[:64]}
            if btn.get("url"):
                kwargs["url"] = btn["url"]
            elif btn.get("callback_data"):
                kwargs["callback_data"] = btn["callback_data"]
            else:
                continue
            rows.setdefault(row_idx, []).append(InlineKeyboardButton(**kwargs))
        return InlineKeyboardMarkup(
            inline_keyboard=[rows[i] for i in sorted(rows)]
        )


class _DictUser:
    """Minimal user-like object from stored DB data for delayed welcome sends."""
    def __init__(self, id: int, first_name: str, last_name=None, username=None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
