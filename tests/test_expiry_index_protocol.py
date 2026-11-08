"""Storage boundary decoding and admission/acknowledgment arguments, without Redis."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from wappa.persistence.redis.expiry_index import RedisExpiryIndex
from wappa.persistence.redis.redis_handler.utils.key_factory import KeyFactory

KEY = "instagram__account:EXPTRIGGER:reminder:opaque-id"


@pytest.mark.parametrize("ttl", [0, -1, 0.5, True])
async def test_invalid_ttl_never_mutates_the_store(ttl):
    client = SimpleNamespace(eval=AsyncMock())
    index = RedisExpiryIndex(client)
    with pytest.raises(ValueError, match="positive"):
        await index.arm(KEY, ttl)
    client.eval.assert_not_awaited()


async def test_every_renewal_writes_a_distinct_occurrence_through_one_atomic_operation():
    client = SimpleNamespace(eval=AsyncMock(return_value=1))
    index = RedisExpiryIndex(client)
    assert await index.arm(KEY, 15)
    assert await index.arm(KEY, 15)
    first, second = client.eval.call_args_list
    assert first.args[1:6] == (
        3,
        KEY,
        KeyFactory.expiry_due(),
        KeyFactory.expiry_records(),
        15,
    )
    assert first.args[-1] != second.args[-1]


@pytest.mark.parametrize("encoded", [False, True])
async def test_claim_decoding_and_acknowledgment_retain_the_exact_occurrence_record(
    encoded,
):
    raw = json.dumps(
        {"generation": "unique-occurrence", "due_at_ms": 1_800_000_000_123}
    )
    client = SimpleNamespace(
        eval=AsyncMock(return_value=[b"indexed", raw.encode() if encoded else raw])
    )
    index = RedisExpiryIndex(client)
    trigger = await index.claim(KEY)
    assert trigger.record == raw
    assert trigger.generation == "unique-occurrence"
    assert trigger.due_at == datetime.fromtimestamp(1_800_000_000.123, UTC)
    client.eval.return_value = 1
    assert await index.acknowledge(trigger)
    assert client.eval.call_args.args[-1] == raw


async def test_unindexed_notifications_have_no_invented_due_time_or_generation():
    client = SimpleNamespace(eval=AsyncMock(return_value=[b"legacy", b""]))
    index = RedisExpiryIndex(client)
    trigger = await index.claim(KEY)
    assert (
        trigger.record is None and trigger.generation is None and trigger.due_at is None
    )
    client.eval.reset_mock()
    assert not await index.acknowledge(trigger)
    client.eval.assert_not_awaited()
