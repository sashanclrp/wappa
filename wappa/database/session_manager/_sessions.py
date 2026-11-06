"""Session acquisition: shielded teardown, eager connect retry, write/read sessions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

import anyio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from wappa.database.session_manager._base import _ManagerBase

logger = logging.getLogger("wappa.database.session_manager")


class _SessionMixin(_ManagerBase):
    """Cancellation-safe write and read session context managers."""

    @staticmethod
    async def _shielded(coro: Awaitable[None], *, timeout: float = 10.0) -> None:
        """
        Run a teardown coroutine shielded from outer cancellation.

        Session teardown (rollback/close) must reach Postgres even when the
        request is being cancelled — otherwise the server-side backend is left
        orphaned mid-transaction (``idle in transaction``) and the pool leaks.

        ``asyncio.CancelledError`` derives from ``BaseException`` (not
        ``Exception``), and every ``BaseHTTPMiddleware`` layer wraps the request
        in an anyio cancel scope, so a plain ``await session.rollback()`` gets
        cancelled before the ROLLBACK/DISCARD is sent. ``move_on_after(shield=True)``
        protects the teardown; the timeout bounds it so a dead connection cannot
        wedge cleanup forever (pairs with ``command_timeout``).

        Args:
            coro: Teardown coroutine to run (e.g. ``session.rollback()``).
            timeout: Maximum seconds to spend on teardown before giving up.
        """
        try:
            with anyio.move_on_after(timeout, shield=True):
                await coro
        except Exception as e:  # noqa: BLE001 - teardown must never mask the real error
            logger.warning("Session teardown failed (ignored): %s", e)

    async def _acquire_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        operation_name: str,
    ) -> AsyncSession:
        """
        Create a session and eagerly establish its connection, retrying only
        transient *connection-establishment* failures.

        The failure this closes is a **brand-new** connection failing to open —
        a DNS blip, connection refused/reset, or unroutable host while the pool
        is growing. ``pool_pre_ping`` already recycles a *stale* pooled
        connection transparently; what it cannot do is retry a fresh connect
        that never succeeds, and that error would otherwise escape into the
        caller's first query where retry is unsafe.

        Retrying here is safe precisely because it happens **before the caller
        runs anything**: no user query has executed, so tearing down a
        half-open session and creating a fresh one is indistinguishable from the
        first attempt. Once the connection is live we return the session and
        never retry again — an in-flight transaction cannot be replayed (that is
        why ``_managed_session`` / ``get_session`` remain non-retrying).

        Forcing the checkout with ``session.connection()`` adds no extra
        round-trip: ``pool_pre_ping`` validates the connection either way; we
        only move the checkout earlier so a connect failure is catchable and
        retryable instead of surfacing mid-handler. Transient classification and
        backoff reuse ``_is_transient_error`` / ``_calculate_backoff``.

        When ``connect_max_retries == 0`` this collapses to fully-lazy
        acquisition (no eager checkout), preserving the minimal transaction
        window and disabling connect retries.

        Args:
            session_maker: Session factory to use.
            operation_name: Name for logging (e.g. "Database", "Read database").

        Returns:
            An ``AsyncSession`` whose connection is already established (or a
            fresh, not-yet-connected session when ``connect_max_retries == 0``).

        Raises:
            Exception: The last transient error after retries are exhausted, or
                immediately for any non-transient / non-``Exception`` failure
                (e.g. ``CancelledError``).
        """
        if self.connect_max_retries <= 0:
            return session_maker()

        attempt = 0
        while True:
            session = session_maker()
            try:
                # Force pool checkout + pre_ping now so a failing connect raises
                # here (retryable) rather than inside the caller's first query.
                await session.connection()
                return session
            except BaseException as exc:
                # Always release the half-open session before retrying/raising.
                await self._shielded(session.close())

                # Never retry cancellation (BaseException, not Exception),
                # non-transient errors (bad creds, SQL), or once exhausted.
                if (
                    not isinstance(exc, Exception)
                    or not self._is_transient_error(exc)
                    or attempt >= self.connect_max_retries
                ):
                    raise

                delay = self._calculate_backoff(attempt)
                logger.warning(
                    "%s connection acquisition failed (attempt %d/%d): %s. "
                    "Retrying in %.2fs...",
                    operation_name,
                    attempt + 1,
                    self.connect_max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

    @asynccontextmanager
    async def _managed_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        operation_name: str = "Database",
    ) -> AsyncIterator[AsyncSession]:
        """
        Yield a session with cancellation-safe commit/rollback/close.

        Connection *establishment* is retried once per transient failure via
        ``_acquire_session`` (bounded by ``connect_max_retries``), before the
        caller runs any query. Beyond that this path is intentionally
        **non-retrying**: the session's transaction begins on the first real
        query, so once the handler is using the session it cannot be safely
        replayed. Dead-connection-at-checkout is covered by ``pool_pre_ping``;
        startup connectivity by ``_initialize_with_retry``. There is no eager
        ``SELECT 1``, so the transaction window still tracks actual query time
        rather than spanning the whole request.

        Teardown runs under ``_shielded`` so cancellation (anyio cancel scope /
        ``asyncio.CancelledError``, both ``BaseException``) cannot prevent the
        ROLLBACK/DISCARD from reaching Postgres.

        Args:
            session_maker: Session factory to use
            operation_name: Name for logging (e.g., "Database", "Read database")

        Yields:
            AsyncSession for database operations
        """
        session = await self._acquire_session(session_maker, operation_name)
        try:
            yield session
            if self.auto_commit:
                await self._shielded(session.commit())
        except BaseException:
            # Catch BaseException (not Exception) so cancellation still rolls back.
            await self._shielded(session.rollback())
            raise
        finally:
            await self._shielded(session.close())

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get write session with cancellation-safe teardown.

        Auto-commits on success if auto_commit=True. Commit/rollback/close run
        shielded from cancellation so the transaction is always resolved on the
        server (see ``_managed_session``). This path does not retry.

        Yields:
            AsyncSession for write operations

        Raises:
            Exception: Propagated unchanged from database operations.
        """
        if not self._initialized or not self._write_session_maker:
            raise RuntimeError("PostgresSessionManager not initialized")

        async with self._managed_session(
            self._write_session_maker, "Database"
        ) as session:
            yield session

    @asynccontextmanager
    async def get_read_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get read session from replica pool (or write if no replicas).

        Uses round-robin selection when multiple replicas are configured.
        Falls back to write database if no replicas available.

        Yields:
            AsyncSession for read operations
        """
        if not self._initialized:
            raise RuntimeError("PostgresSessionManager not initialized")

        # Fallback to write session if no read replicas
        if not self._read_session_makers:
            async with self.get_session() as session:
                yield session
            return

        # Round-robin replica selection
        session_maker = self._read_session_makers[
            self._read_index % len(self._read_session_makers)
        ]
        self._read_index += 1

        async with self._managed_session(session_maker, "Read database") as session:
            yield session
