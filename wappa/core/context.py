"""
Wappa request context and context factory.

Provides a unified container for Wappa infrastructure dependencies
and a factory to create contexts from app.state.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from logging import Logger
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger


@dataclass
class WappaContext:
    """
    Unified request context for Wappa infrastructure access.

    Bundles inbox identity, user identity, and all framework dependencies
    into a single object. Supports two-phase creation where user_id is
    initially None and set later via with_user().
    """

    inbox_id: str
    user_id: str | None = None

    # Infrastructure dependencies
    db: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None
    db_read: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None
    cache_factory: ICacheFactory | None = None
    messenger: IMessenger | None = None

    # Logger
    logger: Logger = field(default_factory=lambda: get_logger("wappa.context"))

    def with_user(self, user_id: str) -> WappaContext:
        """Create a new context with user_id set, preserving all other fields."""
        ctx = copy.copy(self)
        ctx.user_id = user_id
        return ctx


class WappaContextFactory:
    """
    Factory for creating WappaContext instances from app.state.

    Reuses the same connection pools, session managers, and cache backends
    as the WhatsApp webhook pipeline. Stored on app.state.wappa_context_factory
    during startup.
    """

    def __init__(self, app: FastAPI):
        self._app = app
        self.logger = get_logger(__name__)

    async def create_context(
        self,
        inbox_id: str,
        user_id: str | None = None,
        *,
        include_messenger: bool = False,
        platform: PlatformType = PlatformType.WHATSAPP,
    ) -> WappaContext:
        """
        Create a WappaContext with infrastructure dependencies from app.state.

        Args:
            inbox_id: Inbox identifier
            user_id: Optional user identifier (can be set later via ctx.with_user())
            include_messenger: Whether to create a messenger instance
            platform: Messaging platform for messenger creation

        Returns:
            WappaContext with available infrastructure bound
        """
        session_manager = getattr(self._app.state, "postgres_session_manager", None)
        db = session_manager.get_session if session_manager else None
        db_read = session_manager.get_read_session if session_manager else None

        cache_factory = (
            self._create_cache_factory(inbox_id, user_id) if user_id else None
        )

        messenger = None
        if include_messenger:
            messenger = await self._create_messenger(inbox_id, user_id, platform)

        ctx = WappaContext(
            inbox_id=inbox_id,
            user_id=user_id,
            db=db,
            db_read=db_read,
            cache_factory=cache_factory,
            messenger=messenger,
        )

        self.logger.debug(
            "Created WappaContext: inbox=%s, user=%s, db=%s, cache=%s, messenger=%s",
            inbox_id,
            user_id,
            "yes" if db else "no",
            "yes" if cache_factory else "no",
            "yes" if messenger else "no",
        )

        return ctx

    def _create_cache_factory(
        self, inbox_id: str, user_id: str
    ) -> ICacheFactory | None:
        """Create cache factory using same logic as WebhookController."""
        try:
            from wappa.persistence.cache_factory import create_cache_factory

            cache_type = getattr(self._app.state, "wappa_cache_type", "memory")

            if cache_type == "redis":
                redis_manager = getattr(self._app.state, "redis_manager", None)
                if not redis_manager or not redis_manager.is_initialized():
                    self.logger.warning(
                        "Redis requested but not available, skipping cache"
                    )
                    return None

            factory_class = create_cache_factory(cache_type)
            return factory_class(inbox_id=inbox_id, user_id=user_id)

        except Exception as e:
            self.logger.error("Cache factory creation failed: %s", e)
            return None

    async def _create_messenger(
        self,
        inbox_id: str,
        user_id: str | None,
        platform: PlatformType,
    ) -> IMessenger | None:
        """Create messenger using SessionLifecycle provider."""
        try:
            from wappa.domain.factories.messenger_factory import MessengerFactory

            session_lifecycle = getattr(self._app.state, "session_lifecycle", None)
            if not session_lifecycle:
                self.logger.warning(
                    "SessionLifecycle not available, skipping messenger"
                )
                return None

            credential_store = getattr(self._app.state, "inbox_credential_store", None)
            messenger_factory = MessengerFactory(
                credential_store=credential_store,
                session_provider=session_lifecycle.get_session,
            )
            raw_messenger = await messenger_factory.create_messenger(
                platform=platform,
                inbox_id=inbox_id,
            )

            from wappa.core.messaging.pipeline import MessengerPipeline

            messenger_middleware = getattr(self._app.state, "messenger_middleware", ())
            return MessengerPipeline(
                raw=raw_messenger,
                middleware=messenger_middleware,
            )

        except Exception as e:
            self.logger.error("Messenger creation failed: %s", e)
            return None
