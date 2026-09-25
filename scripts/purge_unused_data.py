"""
Purge Unused Data Script

Connects directly to MongoDB and cleans:
1. Approved join_requests > 24 hours old
2. Failed join_requests > 72 hours old
3. Stale pending/scheduled join_requests > 3 days old
4. Users who never started the bot in DM (private_chat_started != True, excluding super admins)

Run:
  python scripts/purge_unused_data.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.database.connection import db_manager


async def main():
    settings = get_settings()
    print("=" * 60)
    print(">>> STARTING DATABASE PURGE OF UNUSED DATA")
    print("=" * 60)
    print(f"Connecting to MongoDB database: {settings.mongodb_database}...")

    await db_manager.connect(settings.mongodb_uri, settings.mongodb_database)
    db = db_manager.db

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_72h = now - timedelta(hours=72)
    cutoff_3d = now - timedelta(days=3)

    jr_col = db["join_requests"]
    users_col = db["users"]

    # Initial counts
    init_jr_count = await jr_col.count_documents({})
    init_users_count = await users_col.count_documents({})
    eligible_users_count = await users_col.count_documents({"private_chat_started": True})

    print(f"\nCurrent Database Counts:")
    print(f"  * Total join_requests:           {init_jr_count}")
    print(f"  * Total users:                   {init_users_count}")
    print(f"  * [PROTECTED] Broadcast-Eligible Users:   {eligible_users_count} (WILL NOT BE DELETED)")

    # 1. Approved join requests older than 24h
    q_approved = {
        "status": "approved",
        "$or": [
            {"updated_at": {"$lt": cutoff_24h}},
            {"created_at": {"$lt": cutoff_24h}},
        ],
    }
    c_approved = await jr_col.count_documents(q_approved)

    # 2. Failed join requests older than 72h
    q_failed = {
        "status": "failed",
        "$or": [
            {"updated_at": {"$lt": cutoff_72h}},
            {"created_at": {"$lt": cutoff_72h}},
        ],
    }
    c_failed = await jr_col.count_documents(q_failed)

    # 3. Stale pending/scheduled older than 3 days
    q_stale = {
        "status": {"$in": ["pending", "scheduled"]},
        "created_at": {"$lt": cutoff_3d},
    }
    c_stale = await jr_col.count_documents(q_stale)

    # 4. Users who never started the bot in DM
    admin_ids = settings.super_admin_id_list
    q_users = {
        "private_chat_started": {"$ne": True},
        "telegram_id": {"$nin": admin_ids},
    }
    c_users = await users_col.count_documents(q_users)

    print(f"\nRecords to be purged:")
    print(f"  * Old Approved join_requests (>24h):  {c_approved}")
    print(f"  * Old Failed join_requests (>72h):    {c_failed}")
    print(f"  * Stale Pending requests (>3 days):   {c_stale}")
    print(f"  * Unused users (never opened DM):     {c_users}")
    print(f"  -----------------------------------------------")
    print(f"  * Total records to delete:            {c_approved + c_failed + c_stale + c_users}")

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("\n[DRY-RUN MODE] No records were deleted.")
        await db_manager.disconnect()
        return

    # Execute deletions
    r_approved = await jr_col.delete_many(q_approved)
    r_failed = await jr_col.delete_many(q_failed)
    r_stale = await jr_col.delete_many(q_stale)
    r_users = await users_col.delete_many(q_users)

    final_jr_count = await jr_col.count_documents({})
    final_users_count = await users_col.count_documents({})
    final_eligible = await users_col.count_documents({"private_chat_started": True})
    total_purged = (
        r_approved.deleted_count
        + r_failed.deleted_count
        + r_stale.deleted_count
        + r_users.deleted_count
    )

    print("\n" + "=" * 60)
    print("PURGE COMPLETED SUCCESSFULLY!")
    print(f"  * Total records purged:          {total_purged}")
    print(f"  * Remaining join_requests:       {final_jr_count} (active/recent only)")
    print(f"  * Remaining users:               {final_users_count}")
    print(f"  * [PROTECTED] Broadcast-Eligible Users:   {final_eligible} (100% PRESERVED)")
    print("=" * 60)

    await db_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
