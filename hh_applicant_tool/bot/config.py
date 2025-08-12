from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BotSettings:
    telegram_token: str
    database_url: str = "sqlite+aiosqlite:////workspace/hh_bot.db"
    oauth_host: str = "127.0.0.1"
    oauth_port: int = 54156
    public_base_url: str = "http://127.0.0.1:54156"  # change to https://your.domain when deployed

    @classmethod
    def from_env(cls) -> "BotSettings":
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        db_url = os.getenv("BOT_DATABASE_URL", cls.database_url)
        host = os.getenv("BOT_OAUTH_HOST", cls.oauth_host)
        port = int(os.getenv("BOT_OAUTH_PORT", str(cls.oauth_port)))
        public = os.getenv("BOT_PUBLIC_BASE_URL", cls.public_base_url)
        return cls(telegram_token=token, database_url=db_url, oauth_host=host, oauth_port=port, public_base_url=public)