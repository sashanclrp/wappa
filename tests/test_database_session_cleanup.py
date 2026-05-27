from __future__ import annotations

import pytest

from wappa.database.session_manager import PostgresSessionManager


class _Engine:
    def __init__(self) -> None:
        self.dispose_calls: list[bool] = []

    async def dispose(self, *, close: bool = True) -> None:
        self.dispose_calls.append(close)


@pytest.mark.asyncio
async def test_cleanup_drops_connections_without_waiting_for_tcp_close() -> None:
    manager = PostgresSessionManager("postgresql+asyncpg://unused/db")
    read_engine = _Engine()
    write_engine = _Engine()
    manager._read_engines = [read_engine]
    manager._write_engine = write_engine

    await manager.cleanup()

    assert read_engine.dispose_calls == [False]
    assert write_engine.dispose_calls == [False]
    assert manager._read_engines == []
    assert manager.write_engine is None
