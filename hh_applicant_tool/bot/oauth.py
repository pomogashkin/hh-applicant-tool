from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Optional

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


# In-memory map: state -> user_id
_PENDING_STATES: dict[str, int] = {}


async def start_oauth_server(settings: BotSettings) -> OAuthServer:
    app = web.Application()

    async def handle_callback(request: web.Request) -> web.Response:
        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")
        if error:
            return web.Response(text=f"Ошибка авторизации: {error}")
        if not code or not state:
            return web.Response(text="Missing code/state", status=400)
        if state not in _PENDING_STATES:
            return web.Response(text="Invalid or expired state", status=400)
        # Store code in app for retrieval by waiter
        request.app["oauth_code"] = (code, state)
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

    user_id = message.from_user.id
    state = secrets.token_urlsafe(24)
    _PENDING_STATES[state] = user_id

    # Start server
    server = await start_oauth_server(settings)

    # Build authorize URL using custom client
    client = ApiClient(client_id=settings.hh_client_id, client_secret=settings.hh_client_secret)
    client.oauth_client.redirect_uri = f"{settings.public_base_url}/oauth/callback"
    client.oauth_client.scope = settings.hh_scope
    client.oauth_client.state = state
    authorize_url = client.oauth_client.authorize_url

    await message.answer(
        "Перейдите по ссылке для авторизации на HH и дождитесь перенаправления на успешную страницу, затем вернитесь в Telegram:\n" + authorize_url
    )

    # Wait for callback
    try:
        # poll app storage until code arrives or timeout
        for _ in range(300):  # up to ~300 seconds
            await asyncio.sleep(1)
            code_state = server.app.get("oauth_code")
            if code_state:
                code, ret_state = code_state
                if ret_state != state:
                    continue
                break
        else:
            await message.answer("⏳ Время ожидания авторизации истекло. Попробуйте ещё раз.")
            await server.runner.cleanup()
            _PENDING_STATES.pop(state, None)
            return
    finally:
        pass

    # Exchange code
    client = ApiClient(client_id=settings.hh_client_id, client_secret=settings.hh_client_secret)
    client.oauth_client.redirect_uri = f"{settings.public_base_url}/oauth/callback"
    token = client.oauth_client.authenticate(code)
    client.handle_access_token(token)

    # Save tokens
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

    _PENDING_STATES.pop(state, None)
    await server.runner.cleanup()

    await message.answer("🔓 Авторизация HH успешно завершена. Теперь можно пользоваться меню.")