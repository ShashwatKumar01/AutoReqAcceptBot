"""
Cleanup service: deletes processed join_requests older than the retention window.

Retention rules:
  - approved + welcome resolved (sent/failed/invite_sent/invite_failed/skipped) → delete after 24h
  - approved + no welcome_status field (welcome not configured)                 → delete after 24h
  - failed (approval failed)                                                    → delete after 72h
  - pending / scheduled older than 3 days                                       → delete (stale)
      Reason: if a user joined via a direct link, Telegram never calls the bot
      again — the request stays pending forever. After 3 days it's dead.
      Telegram itself typically expires join requests after a few days too.

Runs once per day via the approval worker (at 2 AM UTC).
Reports results to super-admin via Telegram.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from aiogram import Bot
from app.core.logging import get_logger


class CleanupService:
    WELCOME_DONE_STATUSES = {
        "sent", "failed", "invite_sent", "invite_failed", "skipped",
    }

    # Stale pending/scheduled: after 3 days they are dead
    STALE_PENDING_DAYS = 3

    def __init__(
        self,
        db,
        bot: Optional[Bot] = None,
        super_admin_chat_ids: list[int] | int | None = None,
        approved_retention_hours: int = 24,
        failed_retention_hours: int = 72,
    ):
        self.db = db
        self.bot = bot
        if isinstance(super_admin_chat_ids, int):
            self.super_admin_chat_ids = [super_admin_chat_ids]
        elif isinstance(super_admin_chat_ids, list):
            self.super_admin_chat_ids = [int(x) for x in super_admin_chat_ids if str(x).lstrip('-').isdigit()]
        else:
            self.super_admin_chat_ids = []
        self.approved_retention = timedelta(hours=approved_retention_hours)
        self.failed_retention = timedelta(hours=failed_retention_hours)
        self.stale_retention = timedelta(days=self.STALE_PENDING_DAYS)
        self.logger = get_logger("cleanup_service")

    async def run_daily_cleanup(
        self,
        purge_non_dm_users: bool = False,
        super_admin_ids: list[int] | None = None,
    ) -> dict:
        """Delete processed and stale join_requests past their retention window."""
        now = datetime.now(timezone.utc)
        stats = {
            "approved_deleted": 0,
            "failed_deleted": 0,
            "stale_deleted": 0,   # pending/scheduled that died silently
            "users_purged": 0,
            "errors": [],
        }
        col = self.db["join_requests"]

        # 1. Delete approved + welcome done
        try:
            cutoff = now - self.approved_retention
            r = await col.delete_many({
                "status": "approved",
                "welcome_status": {"$in": list(self.WELCOME_DONE_STATUSES)},
                "updated_at": {"$lt": cutoff},
            })
            stats["approved_deleted"] += r.deleted_count
        except Exception as e:
            stats["errors"].append(f"approved+welcome: {e}")

        # 2. Delete approved with no welcome_status (welcome was not configured)
        try:
            cutoff = now - self.approved_retention
            r = await col.delete_many({
                "status": "approved",
                "welcome_status": {"$exists": False},
                "updated_at": {"$lt": cutoff},
            })
            stats["approved_deleted"] += r.deleted_count
        except Exception as e:
            stats["errors"].append(f"approved+no-welcome: {e}")

        # 3. Delete failed approvals
        try:
            cutoff = now - self.failed_retention
            r = await col.delete_many({
                "status": "failed",
                "updated_at": {"$lt": cutoff},
            })
            stats["failed_deleted"] = r.deleted_count
        except Exception as e:
            stats["errors"].append(f"failed: {e}")

        # 4. Delete STALE pending/scheduled (older than 3 days)
        #    These are requests where the user joined via another path (direct link,
        #    admin add, etc.) — Telegram never calls us again, so they stay pending forever.
        #    After 3 days (= our max delay cap), they are definitively dead.
        try:
            stale_cutoff = now - self.stale_retention
            r = await col.delete_many({
                "status": {"$in": ["pending", "scheduled"]},
                "created_at": {"$lt": stale_cutoff},
            })
            stats["stale_deleted"] = r.deleted_count
            if r.deleted_count:
                self.logger.info(
                    "Deleted stale pending/scheduled requests",
                    count=r.deleted_count,
                    cutoff=stale_cutoff.isoformat(),
                )
        except Exception as e:
            stats["errors"].append(f"stale: {e}")
            self.logger.error("Stale cleanup failed", error=str(e))

        # 5. Delete users who never started the bot in DM (except superadmins)
        if purge_non_dm_users:
            try:
                admin_ids = super_admin_ids or self.super_admin_chat_ids or []
                r = await self.db["users"].delete_many({
                    "private_chat_started": {"$ne": True},
                    "telegram_id": {"$nin": admin_ids},
                })
                stats["users_purged"] = r.deleted_count
                self.logger.info("Purged non-DM users", count=r.deleted_count)
            except Exception as e:
                stats["errors"].append(f"users purge: {e}")

        total = (
            stats["approved_deleted"]
            + stats["failed_deleted"]
            + stats["stale_deleted"]
            + stats.get("users_purged", 0)
        )
        self.logger.info("Daily cleanup complete", total_deleted=total, stats=stats)

        # Send report to all super-admins (always send, even if 0, so admin knows it ran)
        if self.bot and self.super_admin_chat_ids:
            err_note = (
                f"\n⚠️ Errors: {', '.join(stats['errors'][:2])}"
                if stats["errors"] else ""
            )
            stale_line = (
                f"⏳ Stale pending/scheduled: <b>{stats['stale_deleted']}</b>\n"
                if stats["stale_deleted"] else ""
            )
            users_line = (
                f"👥 Non-DM users purged: <b>{stats['users_purged']}</b>\n"
                if stats.get("users_purged") else ""
            )
            report_msg = (
                f"🗑 <b>DB Cleanup Report</b>\n\n"
                f"✅ Approved (done): <b>{stats['approved_deleted']}</b>\n"
                f"❌ Failed (old): <b>{stats['failed_deleted']}</b>\n"
                f"{stale_line}"
                f"{users_line}"
                f"📦 Total removed: <b>{total}</b>"
                f"{err_note}\n"
                f"⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            for admin_chat_id in self.super_admin_chat_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_chat_id,
                        text=report_msg,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    self.logger.warning("Cleanup report send failed", admin_id=admin_chat_id, error=str(e))

        return stats

    async def cleanup_one_chat(self, chat_id: int) -> int:
        """
        Delete ALL join_requests for a specific chat (used after Leave Group / bot removal).
        Deletes pending, scheduled, approved, and failed — the chat is gone, nothing matters.
        """
        col = self.db["join_requests"]
        r = await col.delete_many({"chat_id": chat_id})
        self.logger.info("Chat cleanup done", chat_id=chat_id, deleted=r.deleted_count)
        return r.deleted_count
