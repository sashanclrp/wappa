import logging
from typing import Any

import pytest

from wappa.core.expiry.connection import ConnectionConfig, RedisConnectionManager
from wappa.persistence.redis.redis_client import RedisClient


class FakeConnection:
    def __init__(self, socket_timeout: int | None = 5) -> None:
        self.socket_timeout = socket_timeout


class FakeConnectionPool:
    connection_kwargs = {"db": 3}


class FakePubSub:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.subscribed_channels: list[str] = []
        self.closed = False
        self.unsubscribed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)

    async def unsubscribe(self) -> None:
        self.unsubscribed = True

    async def close(self) -> None:
        self.closed = True


class FakePubSubWithoutConnection(FakePubSub):
    connection = None

    def __init__(self) -> None:
        self.subscribed_channels: list[str] = []
        self.closed = False
        self.unsubscribed = False


class FakeRedis:
    def __init__(self, pubsub: FakePubSub) -> None:
        self.connection_pool = FakeConnectionPool()
        self.pubsub_instance = pubsub
        self.config_sets: list[tuple[str, str]] = []

    async def config_set(self, key: str, value: str) -> None:
        self.config_sets.append((key, value))

    def pubsub(self, **kwargs: Any) -> FakePubSub:
        assert kwargs == {"ignore_subscribe_messages": True}
        return self.pubsub_instance


@pytest.mark.asyncio
async def test_expiry_pubsub_connection_disables_finite_read_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pubsub = FakePubSub()
    redis = FakeRedis(pubsub)

    async def fake_get(alias: str) -> FakeRedis:
        assert alias == "expiry"
        return redis

    monkeypatch.setattr(RedisClient, "get", fake_get)

    manager = RedisConnectionManager(config=ConnectionConfig(alias="expiry"))
    connection = await manager.connect()

    assert connection.channel == "__keyevent@3__:expired"
    assert pubsub.subscribed_channels == ["__keyevent@3__:expired"]
    assert pubsub.connection.socket_timeout is None
    assert redis.config_sets == [("notify-keyspace-events", "Ex")]

    await manager.disconnect()

    assert pubsub.unsubscribed is True
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_expiry_pubsub_connection_warns_when_connection_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pubsub = FakePubSubWithoutConnection()
    redis = FakeRedis(pubsub)

    async def fake_get(alias: str) -> FakeRedis:
        assert alias == "expiry"
        return redis

    monkeypatch.setattr(RedisClient, "get", fake_get)

    manager = RedisConnectionManager(config=ConnectionConfig(alias="expiry"))

    with caplog.at_level(logging.WARNING):
        await manager.connect()

    assert "expiry listener read timeout could not be disabled" in caplog.text

    await manager.disconnect()
