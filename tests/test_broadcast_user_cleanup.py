import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.broadcast_user_cleanup import remove_user_if_unreachable


@pytest.mark.asyncio
async def test_removes_blocked_user():
    user_repo = MagicMock()
    user_repo.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    settings = MagicMock()
    settings.super_admin_id_list = []

    ok = await remove_user_if_unreachable(
        user_repo, 12345, "user_blocked_bot", settings,
    )
    assert ok is True
    user_repo.collection.delete_one.assert_awaited_once_with({"telegram_id": 12345})


@pytest.mark.asyncio
async def test_skips_super_admin():
    user_repo = MagicMock()
    user_repo.collection.delete_one = AsyncMock()
    settings = MagicMock()
    settings.super_admin_id_list = [999]

    ok = await remove_user_if_unreachable(
        user_repo, 999, "user_blocked_bot", settings,
    )
    assert ok is False
    user_repo.collection.delete_one.assert_not_called()
