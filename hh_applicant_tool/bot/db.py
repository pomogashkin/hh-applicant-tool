from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, ForeignKey, select, func
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_ts: Mapped[int] = mapped_column(Integer, server_default=func.strftime('%s','now'))

    preferences: Mapped["UserPreference"] = relationship(back_populates="user", uselist=False)
    tokens: Mapped["HHTokens"] = relationship(back_populates="user", uselist=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    professional_roles: Mapped[str] = mapped_column(String, default="4,6,8,9,34")
    salary_from: Mapped[int] = mapped_column(Integer, default=100000)
    remote: Mapped[int] = mapped_column(Integer, default=1)  # 1 true, 0 false
    flexible: Mapped[int] = mapped_column(Integer, default=1)  # 1 true, 0 false
    exclude_text: Mapped[str] = mapped_column(String, default="ux ui")
    browse_page: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="preferences")


class HHTokens(Base):
    __tablename__ = "hh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    access_expires_at: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship(back_populates="tokens")


@dataclass
class Database:
    engine
    session_factory: async_sessionmaker[AsyncSession]


async def create_database(database_url: str) -> Database:
    engine = create_async_engine(database_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=session_factory)


async def get_or_create_user(session: AsyncSession, telegram_user_id: int) -> User:
    q = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = q.scalar_one_or_none()
    if user:
        return user
    user = User(telegram_user_id=telegram_user_id)
    session.add(user)
    await session.flush()
    # init defaults
    prefs = UserPreference(user_id=user.id)
    session.add(prefs)
    tok = HHTokens(user_id=user.id)
    session.add(tok)
    await session.commit()
    return user


async def get_user_bundle(session: AsyncSession, telegram_user_id: int):
    q = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = q.scalar_one()
    await session.refresh(user)
    return user