"""
Regression tests for cancellation-safe session teardown (Defect A).

Guards against the connection-leak where ``asyncio.CancelledError`` (a
``BaseException``, raised by every anyio cancel scope / ``BaseHTTPMiddleware``
layer) slips past session teardown, orphaning the server-side backend
``idle in transaction`` until the Supavisor pool is exhausted and the app hangs.

These tests boot a real, ephemeral PostgreSQL cluster (asyncpg + SQLAlchemy do
not otherwise open a real transaction). They are skipped automatically when the
PostgreSQL server binaries (``initdb``/``pg_ctl``) are not installed.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest
from sqlalchemy import text

from wappa.database.session_manager import PostgresSessionManager


def _find_pg_bin(name: str) -> str | None:
    """Locate a PostgreSQL server binary on PATH or the standard Debian layout."""
    found = shutil.which(name)
    if found:
        return found
    for base in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        candidate = base / name
        if candidate.exists():
            return str(candidate)
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_INITDB = _find_pg_bin("initdb")
_PG_CTL = _find_pg_bin("pg_ctl")

requires_postgres = pytest.mark.skipif(
    not (_INITDB and _PG_CTL),
    reason="PostgreSQL server binaries (initdb/pg_ctl) not available",
)


# ---------------------------------------------------------------------------
# Deterministic unit test (no database) — the real regression guard.
#
# Proves the two code-level guarantees of the fix directly, independent of how
# a given driver happens to clean up a cancelled connection:
#   1. Cancellation (BaseException) still triggers rollback — an ``except
#      Exception`` would let CancelledError slip past.
#   2. Teardown is shielded — rollback/close run to *completion* even when the
#      enclosing anyio cancel scope is already cancelled.
# ---------------------------------------------------------------------------


class _FakeSession:
    """Records teardown lifecycle so we can assert it ran to completion."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def commit(self) -> None:
        self.events.append("commit_start")
        await anyio.sleep(0.05)
        self.events.append("commit_done")

    async def rollback(self) -> None:
        self.events.append("rollback_start")
        await anyio.sleep(0.05)
        self.events.append("rollback_done")

    async def close(self) -> None:
        self.events.append("close_start")
        await anyio.sleep(0.05)
        self.events.append("close_done")


@pytest.mark.asyncio
async def test_teardown_completes_when_cancelled_mid_use() -> None:
    manager = PostgresSessionManager("postgresql://u:p@h/db")
    fake = _FakeSession()

    async def use_session() -> None:
        async with manager._managed_session(lambda: fake):
            await anyio.sleep(1.0)  # cancelled by the outer scope below

    # Cancel while the handler is mid-use — the exact BaseHTTPMiddleware shape.
    with anyio.move_on_after(0.1):
        await use_session()

    # Rollback was invoked (BaseException caught) AND completed (shielded).
    assert "rollback_done" in fake.events, fake.events
    # Close ran to completion despite the active cancellation.
    assert "close_done" in fake.events, fake.events
    # No spurious commit on the cancelled path.
    assert "commit_start" not in fake.events, fake.events


@pytest.mark.asyncio
async def test_commit_completes_and_no_rollback_on_success() -> None:
    manager = PostgresSessionManager("postgresql://u:p@h/db")
    fake = _FakeSession()

    async with manager._managed_session(lambda: fake):
        pass  # clean exit -> auto_commit

    assert "commit_done" in fake.events, fake.events
    assert "close_done" in fake.events, fake.events
    assert "rollback_start" not in fake.events, fake.events


@pytest.fixture(scope="module")
def pg_dsn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Boot a throwaway local PostgreSQL cluster and yield an asyncpg DSN."""
    data_dir = tmp_path_factory.mktemp("pgdata")
    sock_dir = tmp_path_factory.mktemp("pgsock")
    port = _free_port()
    logfile = data_dir / "server.log"

    subprocess.run(
        [
            _INITDB,
            "-D",
            str(data_dir),
            "-U",
            "postgres",
            "--auth=trust",
            "-E",
            "UTF8",
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            _PG_CTL,
            "-D",
            str(data_dir),
            "-l",
            str(logfile),
            "-w",
            "-o",
            f"-p {port} -k {sock_dir} -c listen_addresses=127.0.0.1 "
            f"-c fsync=off -c full_page_writes=off",
            "start",
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PGPORT": str(port)},
    )

    try:
        yield f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            [_PG_CTL, "-D", str(data_dir), "-m", "immediate", "-w", "stop"],
            capture_output=True,
        )


async def _idle_in_transaction_count(manager: PostgresSessionManager) -> int:
    """Count server backends stuck ``idle in transaction`` for this database."""
    async with manager.get_read_session() as session:
        result = await session.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'idle in transaction' "
                "AND datname = current_database()"
            )
        )
        return int(result.scalar_one())


async def _cancel_mid_query(manager: PostgresSessionManager) -> None:
    """
    Open a session, start a slow query, then cancel the enclosing cancel scope
    mid-flight — exactly the shape a BaseHTTPMiddleware cancel scope produces.
    """

    async def worker() -> None:
        async with manager.get_session() as session:
            # Long enough that we reliably cancel while BEGIN is open on the server.
            await session.execute(text("SELECT pg_sleep(30)"))

    with anyio.move_on_after(0.5):  # scope cancels the worker after 0.5s
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker)
            await anyio.sleep(30)  # kept alive until the outer scope cancels us


@requires_postgres
@pytest.mark.asyncio
async def test_cancel_mid_query_leaves_no_idle_in_transaction(pg_dsn: str) -> None:
    manager = PostgresSessionManager(pg_dsn, pool_size=5, max_overflow=5)
    await manager.initialize()
    try:
        await _cancel_mid_query(manager)

        # Give the server a beat to register the rolled-back backend as idle/gone.
        await anyio.sleep(0.5)

        assert await _idle_in_transaction_count(manager) == 0

        status = manager.get_health_status()
        assert status["pool_checked_out"] == 0
    finally:
        await manager.cleanup()


@requires_postgres
@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_degrade_pool(pg_dsn: str) -> None:
    manager = PostgresSessionManager(pg_dsn, pool_size=5, max_overflow=5)
    await manager.initialize()
    try:
        for _ in range(8):
            await _cancel_mid_query(manager)

        await anyio.sleep(0.5)

        # No orphaned transactions accumulated across repeated aborts.
        assert await _idle_in_transaction_count(manager) == 0

        # A normal query still succeeds immediately — pool is not degraded.
        start = time.monotonic()
        async with manager.get_session() as session:
            result = await session.execute(text("SELECT 42"))
            assert result.scalar_one() == 42
        assert time.monotonic() - start < 5.0

        assert manager.get_health_status()["pool_checked_out"] == 0
    finally:
        await manager.cleanup()
