"""Pure URL normalization and engine/session-maker construction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def normalize_url(url: str) -> str:
    """
    Normalize database URL to use asyncpg driver.

    Args:
        url: Database connection URL

    Returns:
        URL with postgresql+asyncpg:// scheme
    """
    if url.startswith(("postgresql+asyncpg://", "postgres+asyncpg://")):
        return url

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)

    raise ValueError(
        f"Invalid PostgreSQL URL: {url}. "
        "Expected postgresql://, postgres://, or postgresql+asyncpg://"
    )


def create_engine(
    url: str,
    *,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    pool_recycle: int,
    pool_pre_ping: bool,
    echo: bool,
    statement_cache_size: int | None,
    command_timeout: float | None,
    connect_timeout: float | None,
) -> AsyncEngine:
    """
    Create async engine with configured pool settings.

    Args:
        url: Database connection URL

    Returns:
        Configured AsyncEngine instance
    """
    # Build connect_args from configuration.
    # NOTE: always pass a dict (never None). create_async_engine chokes on
    # connect_args=None (TypeError: 'NoneType' object is not iterable), so an
    # empty dict must stay an empty dict.
    connect_args: dict = {}
    if statement_cache_size is not None:
        connect_args["statement_cache_size"] = statement_cache_size
    if command_timeout is not None:
        connect_args["command_timeout"] = command_timeout
    if connect_timeout is not None:
        connect_args["timeout"] = connect_timeout

    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        echo=echo,
        connect_args=connect_args,
    )


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create session factory for the given engine.

    Args:
        engine: AsyncEngine instance

    Returns:
        async_sessionmaker configured for the engine
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
