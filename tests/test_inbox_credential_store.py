from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from wappa.core.config.settings import settings
from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.wappa_app import Wappa
from wappa.domain.interfaces.inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)
from wappa.domain.services import DatabaseInboxCredentialStore
from wappa.domain.services.inbox_credentials_service import SettingsInboxCredentialStore

INBOX_1 = "inbox-1"


def _credentials_cache_key(inbox_id: str) -> str:
    return f"inbox:{inbox_id}:credentials"


class _FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.expirations: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []

    async def hgetall(self, key: str) -> dict[str, str]:
        self.calls.append(("hgetall", key))
        return self.hashes.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.calls.append(("hset", key))
        self.hashes[key] = dict(mapping)

    async def expire(self, key: str, ttl: int) -> None:
        self.calls.append(("expire", key))
        self.expirations[key] = ttl

    async def delete(self, key: str) -> None:
        self.calls.append(("delete", key))
        self.hashes.pop(key, None)


class _FakeMappings:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def first(self) -> dict[str, Any] | None:
        return self._row


class _FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._row)


class _FakeSession:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.execute_calls = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        self.execute_calls += 1
        return _FakeResult(self.row)


def _session_factory(session: _FakeSession):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


class _CustomStore(IInboxCredentialStore):
    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        return InboxCredentials(inbox_id=inbox_id, access_token="custom-token")

    async def validate_inbox(self, inbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_database_store_cache_hit_skips_database() -> None:
    redis = _FakeRedis()
    redis.hashes[_credentials_cache_key(INBOX_1)] = {
        "access_token": "cached-token",
        "platform_account_id": "waba-1",
        "platform": "whatsapp",
        "is_active": "true",
    }
    session = _FakeSession(row=None)
    store = DatabaseInboxCredentialStore(_session_factory(session), redis)

    credentials = await store.get_credentials(INBOX_1)

    assert credentials == InboxCredentials(
        inbox_id=INBOX_1,
        access_token="cached-token",
        platform_account_id="waba-1",
    )
    assert session.execute_calls == 0


@pytest.mark.asyncio
async def test_database_store_cache_miss_queries_database_and_populates_cache() -> None:
    redis = _FakeRedis()
    session = _FakeSession(
        row={
            "inbox_id": INBOX_1,
            "access_token": "db-token",
            "platform_account_id": "waba-1",
        }
    )
    store = DatabaseInboxCredentialStore(
        _session_factory(session), redis, cache_ttl=123
    )

    credentials = await store.get_credentials(INBOX_1)

    assert credentials == InboxCredentials(
        inbox_id=INBOX_1,
        access_token="db-token",
        platform_account_id="waba-1",
    )
    assert session.execute_calls == 1
    assert redis.hashes[_credentials_cache_key(INBOX_1)]["access_token"] == "db-token"
    assert redis.expirations[_credentials_cache_key(INBOX_1)] == 123


@pytest.mark.asyncio
async def test_database_store_unknown_inbox_raises_without_negative_cache() -> None:
    redis = _FakeRedis()
    session = _FakeSession(row=None)
    store = DatabaseInboxCredentialStore(_session_factory(session), redis)

    with pytest.raises(InboxNotFoundError):
        await store.get_credentials("missing")

    assert session.execute_calls == 1
    assert "inbox:missing:credentials" not in redis.hashes


@pytest.mark.asyncio
async def test_database_store_invalidate_cache_deletes_redis_key() -> None:
    redis = _FakeRedis()
    redis.hashes[_credentials_cache_key(INBOX_1)] = {
        "access_token": "cached-token",
        "is_active": "true",
    }
    session = _FakeSession(row=None)
    store = DatabaseInboxCredentialStore(_session_factory(session), redis)

    await store.invalidate_cache(INBOX_1)

    assert _credentials_cache_key(INBOX_1) not in redis.hashes
    assert ("delete", _credentials_cache_key(INBOX_1)) in redis.calls


@pytest.mark.asyncio
async def test_settings_store_default_behavior_still_uses_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "wp_access_token", "settings-token")
    monkeypatch.setattr(settings, "wp_phone_id", "inbox-1")
    monkeypatch.setattr(settings, "wp_bid", "waba-1")

    store = SettingsInboxCredentialStore()

    assert await store.validate_inbox(INBOX_1) is True
    credentials = await store.get_credentials(INBOX_1)
    assert credentials == InboxCredentials(
        inbox_id=INBOX_1,
        access_token="settings-token",
        platform_account_id="waba-1",
    )


def test_builder_wires_default_settings_store() -> None:
    app = WappaBuilder().build()

    assert isinstance(app.state.inbox_credential_store, SettingsInboxCredentialStore)


def test_builder_wires_custom_inbox_credential_store() -> None:
    store = _CustomStore()
    app = WappaBuilder().with_inbox_credential_store(store).build()

    assert app.state.inbox_credential_store is store


def test_wappa_accepts_custom_inbox_credential_store() -> None:
    store = _CustomStore()
    wappa = Wappa(inbox_credential_store=store)

    assert wappa._builder.inbox_credential_store is store
