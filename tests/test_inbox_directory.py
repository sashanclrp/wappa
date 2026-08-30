"""Inbox Directory contract suite, run on every Table Cache backend (PRD 2/3)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from wappa.core.security import CredentialCodec, SecretBinding
from wappa.domain.inbox import (
    InboxCredentialIntegrityError,
    InboxCredentialService,
    InboxDirectory,
    InboxDirectoryUnavailableError,
    InboxMutationConflictError,
    InboxNotFoundError,
    InboxRef,
    PlatformAccountRef,
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
    dump_record_for_storage,
)
from wappa.domain.inbox.credentials import PlatformAccountEmptyIndexRecord
from wappa.domain.interfaces.cache_interfaces import ITableCache
from wappa.persistence import create_system_table_cache
from wappa.persistence.inbox_directory import (
    ACCOUNT_INDEX_TABLE,
    DIRECTORY_TTL_SECONDS,
    PRIMARY_TABLE,
    InboxDirectoryTable,
)
from wappa.persistence.json.handlers.utils.file_manager import file_manager
from wappa.persistence.redis.redis_client import RedisClient
from wappa.schemas.core.types import PlatformType

REDIS_URL = os.getenv("WAPPA_TEST_REDIS_URL", "redis://localhost:6379")
KEY = CredentialCodec.generate_key()
WABA = PlatformAccountRef.whatsapp("9001")
OTHER_WABA = PlatformAccountRef.whatsapp("9002")
INBOX_1 = InboxRef.whatsapp("111")
INBOX_2 = InboxRef.whatsapp("222")
INBOX_3 = InboxRef.whatsapp("333")


class FakeSource:
    """A Host source over an in-memory durable table."""

    def __init__(self) -> None:
        self.records: dict[InboxRef, Any] = {}
        self.get_calls: list[InboxRef] = []
        self.list_calls: list[PlatformAccountRef] = []
        self.fail = False

    async def get_inbox(self, inbox_ref: InboxRef) -> Any:
        self.get_calls.append(inbox_ref)
        if self.fail:
            raise ConnectionError("database unavailable")
        return self.records.get(inbox_ref)

    async def list_inboxes_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[Any, ...]:
        self.list_calls.append(account_ref)
        if self.fail:
            raise ConnectionError("database unavailable")
        return tuple(
            record
            for record in self.records.values()
            if record.account_ref == account_ref
        )


class FailingTable:
    """Wraps an ITableCache and fails the first N calls of one method."""

    def __init__(self, inner: ITableCache, method: str, failures: int) -> None:
        self._inner = inner
        self._method = method
        self._failures = failures
        self.context_id = inner.context_id  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name != self._method:
            return attr

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            if self._failures > 0:
                self._failures -= 1
                raise ConnectionError("backend down")
            return await attr(*args, **kwargs)

        return wrapped


async def _open_redis_pools() -> bool:
    await RedisClient.close()
    RedisClient.setup_single_url(REDIS_URL)
    try:
        async with RedisClient.connection(alias="table") as redis:
            await redis.ping()
        return True
    except Exception:
        await RedisClient.close()
        return False


async def _wipe(table: ITableCache) -> None:
    await table.delete_table(PRIMARY_TABLE)
    await table.delete_table(ACCOUNT_INDEX_TABLE)


@pytest.fixture(params=["memory", "json", "redis"])
async def backend(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[str]:
    match request.param:
        case "json":
            file_manager._cache_root = tmp_path / "cache"
            file_manager.ensure_cache_directories()
            yield "json"
        case "redis":
            if not await _open_redis_pools():
                pytest.skip(f"No Redis reachable at {REDIS_URL}")
            try:
                yield "redis"
            finally:
                await _wipe(create_system_table_cache("redis"))
                await RedisClient.close()
        case _:
            await _wipe(create_system_table_cache("memory"))
            yield "memory"


@pytest.fixture
def table(backend: str) -> ITableCache:
    return create_system_table_cache(backend)


@pytest.fixture
def source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def service() -> InboxCredentialService:
    return InboxCredentialService(CredentialCodec(KEY))


def _directory(
    source: FakeSource, table: Any, codec: CredentialCodec | None = None
) -> InboxDirectory:
    return InboxDirectory(
        source=source,
        table=InboxDirectoryTable(table),
        codec=codec or CredentialCodec(KEY),
    )


@pytest.fixture
def directory(source: FakeSource, table: ITableCache) -> InboxDirectory:
    return _directory(source, table)


def _active(
    service: InboxCredentialService,
    inbox: InboxRef = INBOX_1,
    account: PlatformAccountRef = WABA,
    *,
    token: str = "token-1",
    version: int = 1,
) -> WhatsAppActiveInboxCredentialRecord:
    return service.create_active_record(
        inbox_ref=inbox,
        account_ref=account,
        access_token=SecretStr(token),
        credential_version=version,
    )


# ── read-through and TTL ────────────────────────────────────────────────────


async def test_cold_inbox_calls_the_source_once_and_populates_the_row(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service)

    first = await directory.resolve_credentials(INBOX_1)
    second = await directory.resolve_credentials(INBOX_1)

    assert first.access_token.get_secret_value() == "token-1"
    assert first.account_ref == WABA
    assert second == first
    assert source.get_calls == [INBOX_1]
    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert row is not None and row["status"] == "active"


async def test_warm_active_reads_renew_the_sliding_ttl(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
    backend: str,
) -> None:
    if backend == "json":
        pytest.skip("JSON backend keeps one file-level TTL per scope")
    source.records[INBOX_1] = _active(service)
    await directory.resolve_credentials(INBOX_1)
    await table.renew_ttl(PRIMARY_TABLE, INBOX_1.cache_namespace, 10)

    await directory.resolve_credentials(INBOX_1)

    assert await table.get_ttl(PRIMARY_TABLE, INBOX_1.cache_namespace) > 10
    assert source.get_calls == [INBOX_1]


async def test_absent_inbox_is_negative_cached_without_renewal(
    directory: InboxDirectory, source: FakeSource, table: ITableCache, backend: str
) -> None:
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(INBOX_3)
    row = await table.get(PRIMARY_TABLE, INBOX_3.cache_namespace)
    assert row is not None and row["status"] == "absent" and row["record"] is None
    assert (
        0
        < await table.get_ttl(PRIMARY_TABLE, INBOX_3.cache_namespace)
        <= DIRECTORY_TTL_SECONDS
    )

    if backend != "json":
        await table.renew_ttl(PRIMARY_TABLE, INBOX_3.cache_namespace, 10)
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(INBOX_3)

    assert source.get_calls == [INBOX_3]
    if backend != "json":
        assert await table.get_ttl(PRIMARY_TABLE, INBOX_3.cache_namespace) <= 10


async def test_inactive_inbox_is_not_found_and_holds_no_token(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = service.create_inactive_record(_active(service))

    with pytest.raises(InboxNotFoundError, match="inactive"):
        await directory.resolve_credentials(INBOX_1)
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(INBOX_1)

    assert source.get_calls == [INBOX_1]
    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert row is not None and row["status"] == "inactive"
    assert "access_token" not in row["record"]
    record = await directory.get_record(INBOX_1)
    assert isinstance(record, WhatsAppInactiveInboxCredentialRecord)


async def test_source_outage_is_unavailable_and_never_negative_cached(
    directory: InboxDirectory, source: FakeSource, table: ITableCache
) -> None:
    source.fail = True

    with pytest.raises(InboxDirectoryUnavailableError):
        await directory.resolve_credentials(INBOX_1)

    assert await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace) is None
    source.fail = False
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(INBOX_1)
    assert len(source.get_calls) == 2


async def test_cache_outage_is_unavailable_not_unknown(
    source: FakeSource, table: ITableCache, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    broken = _directory(source, FailingTable(table, "get", failures=1))

    with pytest.raises(InboxDirectoryUnavailableError):
        await broken.resolve_credentials(INBOX_1)

    assert source.get_calls == []


async def test_concurrent_misses_settle_on_one_consistent_row(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service)

    results = await asyncio.gather(
        *(directory.resolve_credentials(INBOX_1) for _ in range(12))
    )

    assert {r.access_token.get_secret_value() for r in results} == {"token-1"}
    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert row is not None and row["credential_version"] == 1


# ── version and mutation rules ─────────────────────────────────────────────


async def test_refresh_accepts_higher_versions_and_evicts(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    evicted: list[InboxRef] = []
    directory.subscribe_evictions(lambda ref: evicted.append(ref))
    source.records[INBOX_1] = _active(service)
    await directory.resolve_credentials(INBOX_1)

    source.records[INBOX_1] = service.rotate_active_record(
        source.records[INBOX_1], access_token=SecretStr("token-2")
    )
    refreshed = await directory.refresh_inbox(INBOX_1)

    assert refreshed is not None and refreshed.credential_version == 2
    assert evicted == [INBOX_1]
    assert (
        await directory.resolve_credentials(INBOX_1)
    ).access_token.get_secret_value() == "token-2"


async def test_lower_version_refresh_is_rejected_as_stale(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service, version=5)
    await directory.resolve_credentials(INBOX_1)

    source.records[INBOX_1] = _active(service, version=4, token="old")
    with pytest.raises(InboxMutationConflictError, match="older"):
        await directory.refresh_inbox(INBOX_1)

    assert (await directory.resolve_credentials(INBOX_1)).credential_version == 5


async def test_equal_version_identical_retry_is_idempotent_and_repairs_index(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service)
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)
    # Damage the derived index without touching the primary row.
    await table.delete(ACCOUNT_INDEX_TABLE, WABA.cache_namespace)
    await table.upsert(
        ACCOUNT_INDEX_TABLE,
        WABA.cache_namespace,
        PlatformAccountEmptyIndexRecord(
            account_ref=WABA, index_version=7, checked_at=_active(service).updated_at
        ).model_dump(mode="json"),
    )

    evicted: list[InboxRef] = []
    directory.subscribe_evictions(lambda ref: evicted.append(ref))
    await directory.refresh_inbox(INBOX_1)

    index = await table.get(ACCOUNT_INDEX_TABLE, WABA.cache_namespace)
    assert index is not None and index["status"] == "active"
    assert evicted == [INBOX_1]
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)


async def test_equal_version_with_different_data_is_a_conflict(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    await directory.resolve_credentials(INBOX_1)

    source.records[INBOX_1] = _active(service, account=OTHER_WABA, version=1)
    with pytest.raises(InboxMutationConflictError, match="conflicts"):
        await directory.refresh_inbox(INBOX_1)


async def test_deactivation_stores_no_token_removes_membership_and_evicts(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service)
    source.records[INBOX_2] = _active(service, INBOX_2, token="token-2")
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (
        INBOX_1,
        INBOX_2,
    )
    evicted: list[InboxRef] = []
    directory.subscribe_evictions(lambda ref: evicted.append(ref))

    source.records[INBOX_1] = service.create_inactive_record(source.records[INBOX_1])
    inactive = await directory.deactivate_inbox(INBOX_1)

    assert isinstance(inactive, WhatsAppInactiveInboxCredentialRecord)
    assert evicted == [INBOX_1]
    with pytest.raises(InboxNotFoundError):
        await directory.resolve_credentials(INBOX_1)
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_2,)
    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert row is not None and "token" not in str(row)
    assert source.list_calls == [WABA]


async def test_deactivate_rejects_a_source_that_still_reports_active(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)

    with pytest.raises(InboxMutationConflictError, match="still reports"):
        await directory.deactivate_inbox(INBOX_1)


async def test_reactivation_requires_a_higher_lifetime_version(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    source.records[INBOX_1] = service.create_inactive_record(source.records[INBOX_1])
    await directory.deactivate_inbox(INBOX_1)

    source.records[INBOX_1] = _active(service, version=2, token="again")
    with pytest.raises(InboxMutationConflictError):
        await directory.refresh_inbox(INBOX_1)

    source.records[INBOX_1] = _active(service, version=3, token="again")
    record = await directory.refresh_inbox(INBOX_1)
    assert record is not None and record.credential_version == 3
    assert (
        await directory.resolve_credentials(INBOX_1)
    ).access_token.get_secret_value() == "again"
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)


async def test_refresh_of_an_absent_inbox_marks_it_absent_and_drops_membership(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service, version=4)
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)

    del source.records[INBOX_1]
    assert await directory.refresh_inbox(INBOX_1) is None

    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert (
        row is not None and row["status"] == "absent" and row["credential_version"] == 4
    )
    assert await directory.list_inbox_refs_for_platform_account(WABA) == ()
    with pytest.raises(InboxNotFoundError):
        await directory.deactivate_inbox(INBOX_1)


async def test_partial_index_write_repairs_on_retry(
    source: FakeSource, table: ITableCache, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    healthy = _directory(source, table)
    assert await healthy.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)
    source.records[INBOX_2] = _active(service, INBOX_2, token="token-2")

    # Primary row lands, the index update fails, the command raises.
    flaky = _directory(source, FailingTable(table, "replace_if", failures=1))
    with pytest.raises(InboxDirectoryUnavailableError):
        await flaky.refresh_inbox(INBOX_2)
    row = await table.get(PRIMARY_TABLE, INBOX_2.cache_namespace)
    assert row is not None and row["status"] == "active"

    # The same command with the same version completes the index work.
    await healthy.refresh_inbox(INBOX_2)
    assert await healthy.list_inbox_refs_for_platform_account(WABA) == (
        INBOX_1,
        INBOX_2,
    )


async def test_moving_an_inbox_between_accounts_updates_both_indexes(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    source.records[INBOX_2] = _active(service, INBOX_2, OTHER_WABA, token="t2")
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)
    assert await directory.list_inbox_refs_for_platform_account(OTHER_WABA) == (
        INBOX_2,
    )

    source.records[INBOX_1] = service.rotate_active_record(
        source.records[INBOX_1],
        access_token=SecretStr("token-1"),
        account_ref=OTHER_WABA,
    )
    await directory.refresh_inbox(INBOX_1)

    assert await directory.list_inbox_refs_for_platform_account(WABA) == ()
    assert await directory.list_inbox_refs_for_platform_account(OTHER_WABA) == (
        INBOX_1,
        INBOX_2,
    )


# ── Platform Account reverse index ──────────────────────────────────────────


async def test_account_lookup_covers_zero_one_duplicate_and_several_members(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
    backend: str,
) -> None:
    assert await directory.list_inbox_refs_for_platform_account(WABA) == ()
    assert source.list_calls == [WABA]
    # Empty index is cached with a fixed TTL and never renewed.
    assert await directory.list_inbox_refs_for_platform_account(WABA) == ()
    assert source.list_calls == [WABA]
    if backend != "json":
        await table.renew_ttl(ACCOUNT_INDEX_TABLE, WABA.cache_namespace, 10)
        await directory.list_inbox_refs_for_platform_account(WABA)
        assert await table.get_ttl(ACCOUNT_INDEX_TABLE, WABA.cache_namespace) <= 10

    source.records[INBOX_2] = _active(service, INBOX_2, token="t2")
    source.records[INBOX_1] = _active(service, INBOX_1, token="t1")
    source.records[INBOX_3] = service.create_inactive_record(_active(service, INBOX_3))
    # An activation replaces the empty index immediately through refresh.
    await directory.refresh_inbox(INBOX_1)
    await directory.refresh_inbox(INBOX_2)
    await directory.refresh_inbox(INBOX_3)

    assert await directory.list_inbox_refs_for_platform_account(WABA) == (
        INBOX_1,
        INBOX_2,
    )


async def test_active_index_hits_renew_and_skip_the_source(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
    backend: str,
) -> None:
    source.records[INBOX_1] = _active(service)
    await directory.list_inbox_refs_for_platform_account(WABA)
    if backend != "json":
        await table.renew_ttl(ACCOUNT_INDEX_TABLE, WABA.cache_namespace, 10)

    assert await directory.list_inbox_refs_for_platform_account(WABA) == (INBOX_1,)

    assert source.list_calls == [WABA]
    if backend != "json":
        assert await table.get_ttl(ACCOUNT_INDEX_TABLE, WABA.cache_namespace) > 10


@pytest.mark.parametrize("corruption", ["missing", "inactive", "wrong_account"])
async def test_stale_index_members_trigger_exactly_one_repair(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
    corruption: str,
) -> None:
    source.records[INBOX_1] = _active(service)
    source.records[INBOX_2] = _active(service, INBOX_2, token="t2")
    assert await directory.list_inbox_refs_for_platform_account(WABA) == (
        INBOX_1,
        INBOX_2,
    )

    if corruption == "missing":
        await table.delete(PRIMARY_TABLE, INBOX_2.cache_namespace)
    elif corruption == "inactive":
        source.records[INBOX_2] = service.create_inactive_record(
            source.records[INBOX_2]
        )
        await table.upsert(
            PRIMARY_TABLE,
            INBOX_2.cache_namespace,
            {
                "schema_version": 1,
                "status": "inactive",
                "platform": "whatsapp",
                "inbox_id": "222",
                "credential_version": 2,
                "record": dump_record_for_storage(source.records[INBOX_2]),
                "stored_at": source.records[INBOX_2].updated_at.isoformat(),
            },
        )
    else:
        moved = _active(service, INBOX_2, OTHER_WABA, token="t2", version=2)
        source.records[INBOX_2] = moved
        await table.upsert(
            PRIMARY_TABLE,
            INBOX_2.cache_namespace,
            {
                "schema_version": 1,
                "status": "active",
                "platform": "whatsapp",
                "inbox_id": "222",
                "credential_version": 2,
                "record": dump_record_for_storage(moved),
                "stored_at": moved.updated_at.isoformat(),
            },
        )

    members = await directory.list_inbox_refs_for_platform_account(WABA)

    expected = (INBOX_1, INBOX_2) if corruption == "missing" else (INBOX_1,)
    assert members == expected
    assert source.list_calls == [WABA, WABA]


async def test_repair_failure_is_unavailable_not_a_subset(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service)
    source.records[INBOX_2] = _active(service, INBOX_2, token="t2")
    await directory.list_inbox_refs_for_platform_account(WABA)
    await table.delete(PRIMARY_TABLE, INBOX_2.cache_namespace)
    source.fail = True

    with pytest.raises(InboxDirectoryUnavailableError):
        await directory.list_inbox_refs_for_platform_account(WABA)


async def test_source_records_under_the_wrong_account_fail_integrity(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    class LyingSource(FakeSource):
        async def list_inboxes_for_platform_account(
            self, account_ref: PlatformAccountRef
        ) -> tuple[Any, ...]:
            return (_active(service, INBOX_1, OTHER_WABA),)

    lying = _directory(LyingSource(), directory._table._table)  # type: ignore[attr-defined]
    with pytest.raises(InboxCredentialIntegrityError):
        await lying.list_inbox_refs_for_platform_account(WABA)


async def test_source_record_for_another_inbox_fails_integrity(
    source: FakeSource, table: ITableCache, service: InboxCredentialService
) -> None:
    class LyingSource(FakeSource):
        async def get_inbox(self, inbox_ref: InboxRef) -> Any:
            return _active(service, INBOX_2)

    lying = _directory(LyingSource(), table)
    with pytest.raises(InboxCredentialIntegrityError):
        await lying.resolve_credentials(INBOX_1)


async def test_source_returning_a_non_canonical_record_fails_integrity(
    source: FakeSource, table: ITableCache
) -> None:
    class RawSource(FakeSource):
        async def get_inbox(self, inbox_ref: InboxRef) -> Any:
            return {"inbox_id": "111", "access_token": "plain"}

    raw = _directory(RawSource(), table)
    with pytest.raises(InboxCredentialIntegrityError):
        await raw.resolve_credentials(INBOX_1)


# ── encryption boundary ────────────────────────────────────────────────────


async def test_two_inboxes_may_share_one_physical_token(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service, INBOX_1, token="shared")
    source.records[INBOX_2] = _active(service, INBOX_2, token="shared")

    one = await directory.resolve_credentials(INBOX_1)
    two = await directory.resolve_credentials(INBOX_2)

    assert one.access_token.get_secret_value() == two.access_token.get_secret_value()
    assert one.inbox_ref != two.inbox_ref
    assert (
        source.records[INBOX_1].access_token.ciphertext.get_secret_value()
        != source.records[INBOX_2].access_token.ciphertext.get_secret_value()
    )


async def test_plaintext_never_reaches_storage_logs_or_errors(
    directory: InboxDirectory,
    source: FakeSource,
    service: InboxCredentialService,
    table: ITableCache,
) -> None:
    source.records[INBOX_1] = _active(service, token="super-secret-token")
    credentials = await directory.resolve_credentials(INBOX_1)

    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert "super-secret-token" not in str(row)
    assert "super-secret-token" not in repr(credentials)
    assert "super-secret-token" not in repr(source.records[INBOX_1])
    ciphertext = source.records[INBOX_1].access_token.ciphertext.get_secret_value()
    assert ciphertext not in repr(source.records[INBOX_1])
    with pytest.raises(InboxNotFoundError) as exc_info:
        await directory.resolve_credentials(INBOX_3)
    assert "super-secret-token" not in str(exc_info.value)


async def test_ciphertext_copied_between_inboxes_fails_integrity(
    directory: InboxDirectory, source: FakeSource, service: InboxCredentialService
) -> None:
    good = _active(service, INBOX_1)
    source.records[INBOX_2] = WhatsAppActiveInboxCredentialRecord(
        inbox_id="222",
        platform_account_id="9001",
        credential_version=1,
        updated_at=good.updated_at,
        access_token=good.access_token,
    )

    with pytest.raises(InboxCredentialIntegrityError):
        await directory.resolve_credentials(INBOX_2)


async def test_previous_key_cache_reads_rewrite_under_the_active_key(
    source: FakeSource, table: ITableCache
) -> None:
    old_codec = CredentialCodec(KEY)
    source.records[INBOX_1] = InboxCredentialService(old_codec).create_active_record(
        inbox_ref=INBOX_1, account_ref=WABA, access_token=SecretStr("token-1")
    )
    new_key = CredentialCodec.generate_key()
    rotated = _directory(source, table, CredentialCodec(new_key, previous_keys=[KEY]))

    credentials = await rotated.resolve_credentials(INBOX_1)

    assert credentials.access_token.get_secret_value() == "token-1"
    row = await table.get(PRIMARY_TABLE, INBOX_1.cache_namespace)
    assert row is not None
    cached_ciphertext = row["record"]["access_token"]["ciphertext"]
    assert (
        cached_ciphertext
        != source.records[INBOX_1].access_token.ciphertext.get_secret_value()
    )
    binding = SecretBinding(PlatformType.WHATSAPP, "111", "access_token")
    from wappa.domain.inbox import EncryptedSecretEnvelope

    assert (
        CredentialCodec(new_key)
        .decrypt(
            EncryptedSecretEnvelope(ciphertext=SecretStr(cached_ciphertext)),
            binding=binding,
        )
        .encrypted_with_active_key
    )


async def test_a_lost_key_is_an_integrity_failure_not_unknown_inbox(
    source: FakeSource, table: ITableCache, service: InboxCredentialService
) -> None:
    source.records[INBOX_1] = _active(service)
    wrong = _directory(source, table, CredentialCodec(CredentialCodec.generate_key()))

    with pytest.raises(InboxCredentialIntegrityError):
        await wrong.resolve_credentials(INBOX_1)


def test_directory_table_requires_the_system_scope() -> None:
    from wappa.persistence.memory.handlers.table_handler import MemoryTable

    with pytest.raises(ValueError, match="System Scope"):
        InboxDirectoryTable(MemoryTable("owner-1"))
