import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_all_users_target():
    from app.services.broadcast_targets import collect_recipient_ids

    user_repo = MagicMock()
    user_repo.collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[
        {"telegram_id": 1},
        {"telegram_id": 2},
    ])))
    ids = await collect_recipient_ids(
        "all_users",
        user_repo=user_repo,
        chat_repo=MagicMock(),
        join_request_repo=MagicMock(),
    )
    assert ids == [1, 2]
