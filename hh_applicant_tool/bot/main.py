from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from .config import BotSettings
from .db import create_database
from .middlewares import DBSessionMiddleware, HHClientMiddleware
from .handlers import router as main_router
from .auth import router as auth_router


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = BotSettings.from_env()

    db = await create_database(settings.database_url)

    dp = Dispatcher()
    dp.message.middleware(DBSessionMiddleware(db.session_factory))
    dp.callback_query.middleware(DBSessionMiddleware(db.session_factory))
    dp.message.middleware(HHClientMiddleware())
    dp.callback_query.middleware(HHClientMiddleware())

    dp.include_router(auth_router)
    dp.include_router(main_router)

    bot = Bot(settings.telegram_token, parse_mode=None)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()