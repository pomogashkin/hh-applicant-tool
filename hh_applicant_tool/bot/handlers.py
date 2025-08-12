from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_or_create_user, User, UserPreference, HHTokens
from .filters import VacancyFilters, vacancy_to_text
from .hh_async import AsyncHH

router = Router()


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Настроить фильтры", callback_data="filters")
    kb.button(text="📋 Посмотреть вакансии", callback_data="browse")
    kb.button(text="📝 Настройка резюме", callback_data="resume")
    kb.button(text="✉️ Сопроводительное письмо", callback_data="cover")
    kb.button(text="🔔 Уведомления", callback_data="notify")
    kb.adjust(1)
    return kb.as_markup()


def browse_kb(vacancy_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if vacancy_url:
        kb.button(text="🔗 Открыть вакансию", url=vacancy_url)
    kb.button(text="➡️ Дальше", callback_data="next")
    kb.button(text="🏠 В главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    await get_or_create_user(session, message.from_user.id)
    await message.answer(
        "Выберите направление работы. Сейчас доступно: Графический дизайнер.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Графический дизайнер", callback_data="role:design")]]
        ),
    )


@router.callback_query(F.data == "role:design")
async def set_role_design(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    res = await session.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    pref = res.scalar_one_or_none()
    if not pref:
        pref = UserPreference(user_id=user.id)
        session.add(pref)
    pref.professional_roles = "4,6,8,9,34"
    await session.commit()
    await callback.message.edit_text("Профиль обновлен. Теперь настройте фильтры или переходите в меню.")
    await callback.message.answer("Главное меню", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "home")
async def go_home(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "filters")
async def setup_filters(callback: CallbackQuery):
    text = (
        "Фильтры по умолчанию:\n"
        "- Зарплата от 100 000\n"
        "- Удаленно / гибкий график\n"
        "- Исключить: UX UI\n\n"
        "Изменение фильтров через меню будет добавлено позже."
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()


async def _send_vacancy(callback: CallbackQuery, session: AsyncSession, hh: AsyncHH, reset_page: bool = False):
    user = await get_or_create_user(session, callback.from_user.id)

    pref_res = await session.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    pref = pref_res.scalar_one()

    tok_res = await session.execute(select(HHTokens).where(HHTokens.user_id == user.id))
    tok = tok_res.scalar_one_or_none()
    if not tok or not tok.access_token:
        await callback.message.edit_text(
            "Сначала авторизуйтесь в HH через команду /auth (временно).",
            reply_markup=main_menu_kb(),
        )
        await callback.answer()
        return

    if reset_page:
        pref.browse_page = 0
        await session.commit()

    vf = VacancyFilters.from_pref_row(pref)

    # Resolve resume
    resumes = await hh.get("/resumes/mine")
    items = resumes.get("items", [])
    if not items:
        await callback.message.edit_text("Не найдено ни одного резюме. Добавьте резюме на HH.", reply_markup=main_menu_kb())
        await callback.answer()
        return
    resume_id = items[0]["id"]

    page = pref.browse_page

    while True:
        res = await hh.get(
            f"/resumes/{resume_id}/similar_vacancies",
            order_by="publication_time",
            professional_role=vf.professional_roles,
            salary_from=vf.salary_from,
            per_page=1,
            page=page,
        )
        vac_items = res.get("items", [])
        total_pages = res.get("pages", 0)
        if not vac_items:
            await callback.message.edit_text("Подходящих вакансий не найдено.", reply_markup=main_menu_kb())
            await callback.answer()
            return
        v = vac_items[0]

        # local exclude filter by text
        exclude_terms = [t.strip().lower() for t in (vf.exclude_text or "").split() if t.strip()]
        text_blobs = []
        snippet = v.get("snippet") or {}
        for k in ("responsibility", "requirement"):
            val = snippet.get(k)
            if val:
                text_blobs.append(val.lower())
        name = (v.get("name") or "").lower()
        text_blobs.append(name)
        if any(term in "\n".join(text_blobs) for term in exclude_terms):
            page += 1
            if total_pages and page >= total_pages:
                await callback.message.edit_text("Больше вакансий нет.", reply_markup=main_menu_kb())
                await callback.answer()
                return
            continue

        # show vacancy
        text = vacancy_to_text(v)
        url = v.get("alternate_url") or v.get("url")
        await callback.message.edit_text(text, reply_markup=browse_kb(url))

        # update next page
        pref.browse_page = page + 1
        await session.commit()
        await callback.answer()
        return


@router.callback_query(F.data == "browse")
async def browse_vacancies(callback: CallbackQuery, session: AsyncSession, hh: AsyncHH):
    await _send_vacancy(callback, session, hh, reset_page=True)


@router.callback_query(F.data == "next")
async def next_vacancy(callback: CallbackQuery, session: AsyncSession, hh: AsyncHH):
    await _send_vacancy(callback, session, hh, reset_page=False)