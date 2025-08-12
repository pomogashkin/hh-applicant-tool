from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, parse_qs

from aiohttp import web
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hh_applicant_tool.api import ApiClient

from .config import BotSettings
from .db import get_or_create_user, HHTokens


@dataclass
class OAuthServer:
    app: web.Application
    runner: web.AppRunner
    site: web.TCPSite


async def start_oauth_server(settings: BotSettings, on_code_callback) -> OAuthServer:
    app = web.Application()

    async def handle_callback(request: web.Request) -> web.Response:
        code = request.query.get("code")
        state = request.query.get("state")
        if not code:
            return web.Response(text="Missing code", status=400)
        await on_code_callback(code, state)
        return web.Response(text="Авторизация прошла успешно. Можете вернуться в Telegram")

    app.add_routes([web.get("/oauth/callback", handle_callback)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.oauth_host, port=settings.oauth_port)
    await site.start()
    return OAuthServer(app=app, runner=runner, site=site)


router = Router()


@router.message(Command("auth"))
async def cmd_auth(message: Message, session: AsyncSession):
    settings = BotSettings.from_env()

    # Each auth request: start a one-off handler binding user_id
    user_id = message.from_user.id

    code_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def on_code(code: str, state: Optional[str]):
        if not code_future.done():
            code_future.set_result(code)

    server = await start_oauth_server(settings, on_code)

    # Build authorize URL using ApiClient's OAuthClient with redirect_uri pointing to our server
    client = ApiClient()
    client.oauth_client.redirect_uri = f"{settings.public_base_url}/oauth/callback"
    authorize_url = client.oauth_client.authorize_url

    await message.answer(
        "Перейдите по ссылке для авторизации на HH и дождитесь перенаправления на успешную страницу, затем вернитесь в Telegram:\n" + authorize_url
    )

    try:
        code = await asyncio.wait_for(code_future, timeout=300)
    except asyncio.TimeoutError:
        await message.answer("⏳ Время ожидания авторизации истекло. Попробуйте ещё раз.")
        # cleanup server
        await server.runner.cleanup()
        return

    # Exchange code for tokens
    token = client.oauth_client.authenticate(code)
    client.handle_access_token(token)

    # Save tokens to DB
    user = await get_or_create_user(session, user_id)
    res = await session.execute(select(HHTokens).where(HHTokens.user_id == user.id))
    row = res.scalar_one_or_none()
    if not row:
        row = HHTokens(user_id=user.id)
        session.add(row)
    row.access_token = client.access_token
    row.refresh_token = client.refresh_token
    row.access_expires_at = client.access_expires_at
    await session.commit()

    await message.answer("🔓 Авторизация HH успешно завершена. Теперь можно пользоваться меню.")

    # Stop server
    await server.runner.cleanup()