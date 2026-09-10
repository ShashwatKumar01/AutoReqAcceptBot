"""Shared MongoDB / Redis health checks for admin UI."""

import asyncio
from typing import Any


REDIS_USES = [
    "FSM / session state (aiogram)",
    "Command throttling",
    "Broadcast rate limits",
    "Approval duplicate locks",
]


async def check_system_health(db, redis_client: Any | None) -> dict[str, Any]:
    mongo_status = "offline"
    try:
        await asyncio.wait_for(db.command("ping"), timeout=2.0)
        mongo_status = "online"
    except Exception:
        pass

    redis_status = "not_configured"
    if redis_client is not None:
        redis_status = "offline"
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=1.0)
            redis_status = "online"
        except Exception:
            pass

    return {
        "mongodb": mongo_status,
        "redis": redis_status,
        "redis_used_for": REDIS_USES,
    }
