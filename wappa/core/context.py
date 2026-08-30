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
from typing import TYPE_CHECKING

from wappa.core.logging.logger import ContextLogger, get_logger
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
    logger: ContextLogger = field(default_factory=lambda: get_logger("wappa.context"))

    def with_user(self, user_id: str) -> WappaContext:
        """Create a new context with user_id set, preserving all other fields."""
        ctx = copy.copy(self)
        ctx.user_id = user_id
        return ctx


class WappaContextFactory:
    """
    Factory for creating WappaContext instances from app.state.

    Delegates to the shared ``DispatchContextBuilder`` so cron jobs and
    External Webhook Sources bind the same capabilities as webhook intake.
    Stored on app.state.wappa_context_factory during startup.
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
            inbox_id: Inbox identifier. A db-only context (no user, no
                messenger) does not validate it, so system-level work may
                pass a placeholder.

        Raises:
            InboxDirectoryError: the Inbox Directory could not answer for this
                Inbox. Cron and External Webhook Source callers see the typed
                category instead of a silently context-less handler.
            user_id: Optional user identifier (can be set later via ctx.with_user())
            include_messenger: Whether to create a messenger instance
            platform: Messaging platform for messenger creation

        Returns:
            WappaContext with available infrastructure bound
        """
        from wappa.core.dispatch.context_builder import (
            DispatchContextBuilder,
            resolve_database_factories,
        )
        from wappa.domain.inbox.errors import InboxDirectoryError
        from wappa.domain.inbox.identity import InboxRef

        builder: DispatchContextBuilder | None
        try:
            builder = DispatchContextBuilder.from_app(self._app)
            db, db_read = builder.database_factories()
        except RuntimeError as exc:
            # The application has not finished startup. Fall back to the same
            # helper every dispatch path uses, so there is one definition of
            # what ``db`` / ``db_read`` mean.
            self.logger.warning("Dispatch Context builder unavailable: %s", exc)
            builder = None
            db, db_read = resolve_database_factories(
                getattr(self._app.state, "postgres_session_manager", None)
            )

        cache_factory: ICacheFactory | None = None
        messenger: IMessenger | None = None
        if builder is not None and (user_id or include_messenger):
            inbox_ref = InboxRef(platform=platform, inbox_id=inbox_id)
            if user_id:
                try:
                    cache_factory = builder.cache_factory(inbox_ref, user_id)
                except InboxDirectoryError:
                    # A directory failure is a typed category the caller must
                    # see. Degrading to cache_factory=None would surface later
                    # as an unclassified AttributeError inside Host code.
                    raise
                except Exception as e:
                    self.logger.error("Cache factory creation failed: %s", e)
            if include_messenger:
                try:
                    messenger = await builder.messenger(inbox_ref)
                except InboxDirectoryError:
                    raise
                except Exception as e:
                    self.logger.error(
                        "Messenger creation failed for %s: %s: %s",
                        inbox_ref,
                        type(e).__name__,
                        e,
                    )

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
