import functools
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    bot_token: str = Field(alias='BOT_TOKEN')

    mongodb_uri: str = Field(alias='MONGODB_URI')
    mongodb_database: str = Field(default='RequestAcceptBot', alias='MONGODB_DATABASE')

    redis_url: str = Field(alias='REDIS_URL')

    webhook_host: str | None = Field(default=None, alias='WEBHOOK_HOST')
    webhook_url: str | None = Field(default=None, alias='WEBHOOK_URL')
    webhook_secret: str | None = Field(default=None, alias='WEBHOOK_SECRET')
    webhook_path: str = Field(default='/webhook', alias='WEBHOOK_PATH')

    # Keep as str at the pydantic layer so env values like "123,456" don't go
    # through pydantic-settings' JSON decoder. Parse into list[int] via validator.
    super_admin_ids: str = Field(default='', alias='SUPER_ADMIN_IDS')

    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    environment: str = Field(default='development', alias='ENVIRONMENT')

    app_host: str = Field(default='0.0.0.0', alias='APP_HOST')
    app_port: int = Field(default=8000, alias='APP_PORT')

    approval_poll_interval: int = Field(default=10, alias='APPROVAL_POLL_INTERVAL')
    broadcast_batch_size: int = Field(default=30, alias='BROADCAST_BATCH_SIZE')
    broadcast_rate_limit: int = Field(default=30, alias='BROADCAST_RATE_LIMIT')

    max_connected_chats_free: int = Field(default=3, alias='MAX_CONNECTED_CHATS_FREE')
    max_broadcast_recipients_free: int = Field(default=1000, alias='MAX_BROADCAST_RECIPIENTS_FREE')

    admin_api_secret: str = Field(default='', alias='ADMIN_API_SECRET')
    admin_web_enabled: bool = Field(default=True, alias='ADMIN_WEB_ENABLED')

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    @field_validator('super_admin_ids', mode='before')
    @classmethod
    def parse_super_admin_ids_raw(cls, v) -> str:
        # Coerce to str (handles list from .env parsers, None, etc.)
        if v is None:
            return ''
        if isinstance(v, list):
            return ','.join(str(x) for x in v)
        return str(v)

    @field_validator('environment', mode='before')
    @classmethod
    def strip_environment_comment(cls, v) -> str:
        """Railway env vars copied from .env.example can carry inline
        comments like 'production  # production or development'. Strip
        anything after a '#', then whitespace, so is_production works."""
        if v is None:
            return 'development'
        s = str(v).split('#', 1)[0].strip().lower()
        return s or 'development'

    @property
    def super_admin_id_list(self) -> list[int]:
        """Parsed list of super admin telegram IDs."""
        if not self.super_admin_ids:
            return []
        return [int(x.strip()) for x in self.super_admin_ids.split(',') if x.strip().isdigit()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == 'production'

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == 'development'

    @property
    def admin_web_url(self) -> str:
        """Public URL for the super-admin web dashboard."""
        if self.webhook_url:
            base = self.webhook_url.rstrip('/')
            path = (self.webhook_path or '/webhook').rstrip('/')
            if base.endswith(path):
                base = base[: -len(path)]
            return f"{base}/admin/"
        return f"http://{self.app_host}:{self.app_port}/admin/"

@functools.lru_cache()
def get_settings() -> Settings:
    return Settings()
