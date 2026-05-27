"""Unified HTTP session lifecycle with draining awareness and serialized recreation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class SessionLifecycle:
    """Owns the Wappa HTTP session lifecycle.

    Provides a single acquisition API consumed by all messenger
    construction paths.  Distinguishes three states:

    - **active**: session is valid and reusable
    - **recoverable**: session is closed but runtime is active — recreation allowed
    - **draining**: runtime is shutting down — new messaging rejected
    """

    def __init__(
        self,
        session: httpx.AsyncClient,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._session = session
        self._client_factory = client_factory or self._default_client_factory
        self._draining = False
        self._recreation_lock = asyncio.Lock()

    def get_session(self) -> httpx.AsyncClient:
        """Return the current session.

        Raises RuntimeDrainingError if the runtime is shutting down.
        Raises HTTPSessionClosedError if the session is closed and
        not recoverable from this synchronous path.
        """
        if self._draining:
            raise RuntimeDrainingError(
                "Wappa runtime is draining — outbound messaging is no longer "
                "accepted. This occurs during server shutdown or hot-reload. "
                "In-flight work should complete before this point."
            )
        if self._session is None or getattr(self._session, "is_closed", False):
            raise HTTPSessionClosedError(
                "httpx.AsyncClient is closed — call SessionLifecycle.recreate() "
                "or WappaCorePlugin.recreate_http_session(app) to restore it."
            )
        return self._session

    async def recreate(self) -> httpx.AsyncClient:
        """Recreate the HTTP session.  Serialized via lock.

        Raises RuntimeDrainingError if shutdown has begun.
        """
        draining_msg = "Cannot recreate HTTP session — Wappa runtime is draining."
        if self._draining:
            raise RuntimeDrainingError(draining_msg)
        async with self._recreation_lock:
            if self._draining:
                raise RuntimeDrainingError(draining_msg)
            if self._session and not self._session.is_closed:
                return self._session

            self._session = self._client_factory()
            logger.info("HTTP session recreated successfully")
            return self._session

    def begin_drain(self) -> None:
        """Mark the session lifecycle as draining."""
        self._draining = True
        logger.info("Session lifecycle entering drain state")

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()
            logger.info("HTTP session closed")
        self._session = None

    @property
    def is_draining(self) -> bool:
        return self._draining

    @property
    def session(self) -> httpx.AsyncClient | None:
        """Raw session reference for backward compat (app.state.http_session)."""
        return self._session

    @staticmethod
    def _default_client_factory() -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(30.0))
