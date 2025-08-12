from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BotSettings:
    telegram_token: str
    database_url: str = "sqlite+aiosqlite:////workspace/hh_bot.db"

    @classmethod
    def from_env(cls) -> "BotSettings":
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        db_url = os.getenv("BOT_DATABASE_URL", cls.database_url)
        return cls(telegram_token=token, database_url=db_url)