from app.core.welcome_defaults import DEFAULT_WELCOME_TEXT
from app.database.repositories import ChatRepository


async def seed_welcome_settings_if_missing(chat_repo: ChatRepository, chat_id: int) -> None:
    """First-time chat connect: enable welcome with default {chat_title} template."""
    existing = await chat_repo.get_settings(chat_id)
    if existing is not None:
        return
    await chat_repo.upsert_settings(
        int(chat_id),
        {
            "welcome_enabled": True,
            "welcome_trigger": "on_approval",
            "welcome_text": DEFAULT_WELCOME_TEXT,
            "welcome_parse_mode": "HTML",
            "welcome_frequency": "every_join",
        },
    )
