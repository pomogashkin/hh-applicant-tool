from __future__ import annotations

import json
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import User, HHTokens, get_or_create_user

router = Router()


@router.message(Command("auth"))
async def cmd_auth(message: Message, session: AsyncSession):
    text = (
        "Отправьте JSON токена HH в ответ на это сообщение (временно, MVP).\n"
        "Пример: {\"access_token\":\"...\", \"refresh_token\":\"...\", \"access_expires_at\": 1234567890}"
    )
    await message.answer(text)


@router.message()
async def paste_token(message: Message, session: AsyncSession):
    if not message.reply_to_message:
        return
    if "токена HH" not in (message.reply_to_message.text or ""):
        return
    try:
        data = json.loads(message.text)
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        access_expires_at = data.get("access_expires_at") or data.get("expires_in")
        if not access_token or not refresh_token:
            await message.answer("Неверный формат токена")
            return
        user = await get_or_create_user(session, message.from_user.id)
        result = await session.execute(select(HHTokens).where(HHTokens.user_id == user.id))
        row = result.scalar_one_or_none()
        if not row:
            row = HHTokens(user_id=user.id)
            session.add(row)
        row.access_token = access_token
        row.refresh_token = refresh_token
        # Normalize expires
        if isinstance(access_expires_at, int):
            row.access_expires_at = access_expires_at
        session.add(row)
        await session.commit()
        await message.answer("Токен сохранен. Теперь можно пользоваться меню.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")