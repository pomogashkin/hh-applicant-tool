from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Awaitable, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from hh_applicant_tool.api import ApiClient

from .db import HHTokens
from .hh_async import AsyncHH
from .config import BotSettings


class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory):
        super().__init__()
        self._session_factory = session_factory

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]) -> Any:
        async with self._session_factory() as session:  # type: AsyncSession
            data["session"] = session
            return await handler(event, data)


class HHClientMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]) -> Any:
        session: AsyncSession = data.get("session")
        user_id = None
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, "message") and event.message and event.message.from_user:
            user_id = event.message.from_user.id

        hh_client = None
        if user_id is not None:
            # Load tokens for user if present
            result = await session.execute(
                # noqa: E501
                "SELECT access_token, refresh_token, access_expires_at FROM hh_tokens ht JOIN users u ON u.id = ht.user_id WHERE u.telegram_user_id = :uid",
                {"uid": user_id},
            )
            row = result.first()
            if row:
                access_token, refresh_token, access_expires_at = row
                settings = BotSettings.from_env()
                client = ApiClient(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    access_expires_at=access_expires_at,
                    client_id=settings.hh_client_id,
                    client_secret=settings.hh_client_secret,
                )
                hh_client = AsyncHH(client)
        if hh_client:
            data["hh"] = hh_client
        return await handler(event, data)