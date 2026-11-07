"""A reconnect callback reaches the Host after a full offboard (ADR-0032).

Runs the real controller, Inbound Runtime, WhatsApp routing and Inbox Directory.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from wappa.api.controllers.webhook_controller import WebhookController
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import MetaCallbackAuthenticator
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.security import CredentialCodec
from wappa.domain.inbox import (
    InboxCredentialService,
    InboxDirectory,
    InboxDirectoryUnavailableError,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
)
from wappa.persistence import create_system_table_cache
from wappa.persistence.inbox_directory import (
    ACCOUNT_INDEX_TABLE,
    PRIMARY_TABLE,
    InboxDirectoryTable,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboxConnectionState, InboxConnectionWebhook
from wappa.webhooks.whatsapp.routing import route_whatsapp_payload

WABA_ID = "9000000001"
PHONE_1 = "111111111111111"
FOREIGN_PHONE = "333333333333333"
APP_SECRET = SecretStr("meta-app-secret")
META_CONFIG = MetaApplicationConfig(
    app_secret=APP_SECRET, whatsapp_webhook_verify_token=SecretStr("verify")
)
WABA = PlatformAccountRef.whatsapp(WABA_ID)
OTHER_WABA = PlatformAccountRef.whatsapp("9000000002")
INBOX_1 = InboxRef.whatsapp(PHONE_1)
INBOX_2 = InboxRef.whatsapp("222222222222222")
FOREIGN = InboxRef.whatsapp(FOREIGN_PHONE)


class _Source:
    def __init__(self) -> None:
        self.records: dict[InboxRef, Any] = {}
        self.fail = False

    async def get_inbox(self, inbox_ref: InboxRef) -> Any:
        if self.fail:
            raise ConnectionError("database unavailable")
        return self.records.get(inbox_ref)

    async def list_inboxes_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[Any, ...]:
        if self.fail:
            raise ConnectionError("database unavailable")
        return tuple(r for r in self.records.values() if r.account_ref == account_ref)


class _Handler(WappaEventHandler):
    """Records what each clone received; shared lists survive ``with_context``."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[dict[str, Any]] = []
        self.messages: list[str] = []
        self.on_connection: Any = None

    async def process_message(self, webhook: Any) -> None:
        self.messages.append(self.inbox_id or "")

    async def process_inbox_connection(self, webhook: InboxConnectionWebhook) -> None:
        self.seen.append(
            {
                "inbox_ref": self.inbox_ref,
                "state": webhook.state,
                "account_id": webhook.account_id,
                "messenger": self.messenger,
                "whatsapp": self.whatsapp,
                "has_cache": self.cache_factory is not None,
            }
        )
        if self.on_connection is not None:
            await self.on_connection(self)


class _NoNetwork:
    async def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an inactive delivery must not call Meta")


@pytest.fixture
async def world() -> AsyncIterator[SimpleNamespace]:
    table = create_system_table_cache("memory")
    await table.delete_table(PRIMARY_TABLE)
    await table.delete_table(ACCOUNT_INDEX_TABLE)
    codec = CredentialCodec(CredentialCodec.generate_key())
    service = InboxCredentialService(codec)
    source = _Source()
    directory = InboxDirectory(
        source=source, table=InboxDirectoryTable(table), codec=codec
    )
    handler = _Handler()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                session_lifecycle=SessionLifecycle(_NoNetwork()),
                inbox_runtime=InboxRuntimeConfiguration(
                    mode=InboxRoutingMode.EXPLICIT, credential_resolver=directory
                ),
                meta_application_config=META_CONFIG,
                messenger_middleware=[],
                wappa_cache_type="memory",
                background_work_tracker=BackgroundWorkTracker(),
            )
        )
    )
    yield SimpleNamespace(
        source=source,
        service=service,
        directory=directory,
        handler=handler,
        request=request,
        controller=WebhookController(WappaEventDispatcher(handler)),
    )
    await table.delete_table(PRIMARY_TABLE)
    await table.delete_table(ACCOUNT_INDEX_TABLE)


async def _activate(world: SimpleNamespace, ref: InboxRef, account=WABA) -> None:
    previous = world.source.records.get(ref)
    world.source.records[ref] = world.service.create_active_record(
        inbox_ref=ref,
        account_ref=account,
        access_token=SecretStr(f"token-{ref.inbox_id}"),
        credential_version=previous.credential_version + 1 if previous else 1,
    )
    await world.directory.refresh_inbox(ref)


async def _offboard(world: SimpleNamespace, *refs: InboxRef) -> None:
    """The Host's offboard: commit inactive records, then refresh the directory."""
    for ref in refs:
        world.source.records[ref] = world.service.create_inactive_record(
            world.source.records[ref]
        )
    for ref in refs:
        await world.directory.deactivate_inbox(ref)


def _reconnect(*, waba: str = WABA_ID, phone: str | None = PHONE_1) -> dict[str, Any]:
    value: dict[str, Any] = {"waba_id": waba, "timestamp": 1710000000}
    if phone is not None:
        value["phone_number_id"] = phone
    return _batch(waba, {"field": "account_reconnected", "value": value})


def _batch(waba: str, *changes: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": waba, "changes": list(changes)}],
    }


def _message_change(phone: str = PHONE_1) -> dict[str, Any]:
    return {
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "15550000000",
                "phone_number_id": phone,
            },
            "contacts": [{"profile": {"name": "U"}, "wa_id": "5730"}],
            "messages": [
                {
                    "from": "5730",
                    "id": "wamid.reconnect-1",
                    "timestamp": "1710000000",
                    "type": "text",
                    "text": {"body": "hi"},
                }
            ],
        },
    }


async def _post(
    world: SimpleNamespace, payload: dict[str, Any], *, signature: str | None = None
) -> Any:
    body = json.dumps(payload).encode()
    result = await world.controller.process_webhook(
        request=world.request,
        platform="whatsapp",
        body=body,
        signature=signature or MetaCallbackAuthenticator(APP_SECRET).sign(body),
    )
    await world.request.app.state.background_work_tracker.drain(timeout=2)
    world.request.app.state.background_work_tracker = BackgroundWorkTracker()
    return result


async def _refused(world: SimpleNamespace, payload: dict[str, Any], **kw: Any) -> int:
    with pytest.raises(HTTPException) as exc_info:
        await _post(world, payload, **kw)
    return exc_info.value.status_code


# ── the recovery path ───────────────────────────────────────────────────────


async def test_phone_addressed_reconnect_reaches_the_host_after_full_offboard(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    assert await _post(world, _reconnect()) == {"status": "accepted"}

    (seen,) = world.handler.seen
    assert seen["inbox_ref"] == INBOX_1
    assert seen["state"] is InboxConnectionState.RECONNECTED
    assert seen["account_id"] == WABA_ID
    assert seen["messenger"] is None and seen["whatsapp"] is None
    assert seen["has_cache"] is True


async def test_account_only_reconnect_fans_out_to_every_inactive_member(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _activate(world, INBOX_2)
    await _offboard(world, INBOX_1, INBOX_2)

    await _post(world, _reconnect(phone=None))

    assert [s["inbox_ref"] for s in world.handler.seen] == [INBOX_1, INBOX_2]
    assert all(s["messenger"] is None for s in world.handler.seen)


async def test_mixed_account_gets_each_member_once_with_the_right_capabilities(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _activate(world, INBOX_2)
    await _offboard(world, INBOX_2)

    await _post(world, _reconnect(phone=None))

    by_inbox = {s["inbox_ref"]: s for s in world.handler.seen}
    assert len(world.handler.seen) == 2
    assert by_inbox[INBOX_1]["messenger"] is not None
    assert by_inbox[INBOX_2]["messenger"] is None


async def test_host_restores_then_scope_is_send_capable_and_messages_flow(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)
    scoped: list[Any] = []

    async def restore(handler: _Handler) -> None:
        await _activate(world, INBOX_1)
        async with handler.scope() as ready:
            scoped.append(ready.messenger)

    world.handler.on_connection = restore
    await _post(world, _reconnect())

    assert scoped and scoped[0] is not None
    assert world.handler.seen[0]["messenger"] is None

    await _post(world, _batch(WABA_ID, _message_change()))
    assert world.handler.messages == [PHONE_1]


async def test_duplicate_reconnect_is_delivered_again_for_the_host_to_ignore(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    await _post(world, _reconnect())
    await _post(world, _reconnect())

    assert len(world.handler.seen) == 2


async def test_duplicate_after_restore_arrives_as_ordinary_active_delivery(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)
    await _activate(world, INBOX_1)

    await _post(world, _reconnect())

    assert world.handler.seen[0]["messenger"] is not None


async def test_refresh_failing_in_the_host_leaves_the_inbox_recoverable(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    async def fail(_handler: _Handler) -> None:
        raise ConnectionError("commit failed")

    world.handler.on_connection = fail
    assert await _post(world, _reconnect()) == {"status": "accepted"}

    world.handler.on_connection = None
    await _post(world, _reconnect())
    assert len(world.handler.seen) == 2
    with pytest.raises(InboxNotFoundError):
        await world.directory.resolve_credentials(INBOX_1)


# ── what stays refused ──────────────────────────────────────────────────────


async def test_bad_signature_is_401_before_any_routing(world: SimpleNamespace) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    assert await _refused(world, _reconnect(), signature="sha256=bad") == 401
    assert world.handler.seen == []


async def test_unknown_inbox_and_unknown_account_are_refused(
    world: SimpleNamespace,
) -> None:
    assert await _refused(world, _reconnect(phone="404404404404404")) == 400
    assert await _refused(world, _reconnect(waba="4040404040", phone=None)) == 400
    assert world.handler.seen == []


async def test_inactive_inbox_of_another_account_is_a_membership_refusal(
    world: SimpleNamespace,
) -> None:
    await _activate(world, FOREIGN, OTHER_WABA)
    await _offboard(world, FOREIGN)

    assert await _refused(world, _reconnect(phone=FOREIGN_PHONE)) == 400
    assert world.handler.seen == []


async def test_account_only_reconnect_never_touches_another_account(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _activate(world, FOREIGN, OTHER_WABA)
    await _offboard(world, INBOX_1, FOREIGN)

    await _post(world, _reconnect(phone=None))

    assert [s["inbox_ref"] for s in world.handler.seen] == [INBOX_1]


async def test_instagram_inbox_with_the_same_raw_id_is_never_used(
    world: SimpleNamespace,
) -> None:
    instagram = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=PHONE_1)
    instagram_account = PlatformAccountRef(
        platform=PlatformType.INSTAGRAM, platform_account_id=PHONE_1
    )
    await _activate(world, instagram, instagram_account)
    await _offboard(world, instagram)

    assert await _refused(world, _reconnect()) == 400
    assert await _refused(world, _reconnect(waba=PHONE_1, phone=None)) == 400
    assert world.handler.seen == []


async def test_ordinary_message_to_an_inactive_inbox_stays_refused(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    assert await _refused(world, _batch(WABA_ID, _message_change())) == 400
    assert world.handler.messages == []


async def test_offboard_event_is_not_a_lifecycle_exception(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)
    offboarded = {
        "field": "account_offboarded",
        "value": {"waba_id": WABA_ID, "timestamp": 1, "reason": "USER_INITIATED"},
    }

    assert await _refused(world, _batch(WABA_ID, offboarded)) == 400


async def test_batch_with_a_refused_item_schedules_nothing(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)
    batch = _batch(
        WABA_ID,
        _reconnect()["entry"][0]["changes"][0],
        _message_change(),
    )

    assert await _refused(world, batch) == 400
    assert world.handler.seen == []


async def test_source_outage_is_503_so_meta_retries(world: SimpleNamespace) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)
    world.source.fail = True

    assert await _refused(world, _reconnect(phone=None)) == 503


async def test_inactive_delivery_carries_no_credentials(world: SimpleNamespace) -> None:
    await _activate(world, INBOX_1)
    await _offboard(world, INBOX_1)

    (delivery,) = await route_whatsapp_payload(_reconnect(), world.directory)

    assert delivery.credentials is None
    assert delivery.inbox_ref == INBOX_1 and delivery.account_ref == WABA


async def test_directory_reads_of_inactive_members_decrypt_nothing(
    world: SimpleNamespace,
) -> None:
    await _activate(world, INBOX_1)
    await _activate(world, INBOX_2)
    await _offboard(world, INBOX_2)

    assert await world.directory.get_inactive_inbox_account(INBOX_2) == WABA
    assert await world.directory.list_inactive_inbox_refs_for_platform_account(
        WABA
    ) == (INBOX_2,)
    world.source.fail = True
    with pytest.raises(InboxDirectoryUnavailableError):
        await world.directory.list_inactive_inbox_refs_for_platform_account(WABA)
