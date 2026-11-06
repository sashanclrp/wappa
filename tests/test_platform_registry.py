"""The Platform Registry is the one installed-Platform set (ADR-0023).

Every shared reader (webhook controller, field registry, Messenger factory,
credential service, HTTP route platform) answers from ``PLATFORMS`` or the
tables beside it, and an uninstalled ``PlatformType`` fails loudly instead of
falling through to WhatsApp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, SecretStr

from wappa.api.routes.messaging_router import create_messaging_router
from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.core.inbound.runtime import InboundRuntime
from wappa.core.security import CredentialCodec
from wappa.domain.factories import MessengerFactory
from wappa.domain.inbox import InboxCredentialService, InboxRef, PlatformAccountRef
from wappa.domain.inbox.credentials import RECORD_TYPES
from wappa.domain.inbox.errors import InboxDirectoryUnavailableError
from wappa.domain.inbox.ports import ResolvedInboxCredentials
from wappa.persistence.inbox_directory import InboxDirectoryTable
from wappa.platforms import BUILTIN_FIELDS, PLATFORMS, build_platforms
from wappa.schemas.core.types import MessageStatus, PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import InboxBase, UserBase
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    InboundMessageWebhook,
    StatusWebhook,
)
from wappa.webhooks.instagram.models import InstagramTextMessage

INSTALLED = {PlatformType.WHATSAPP, PlatformType.INSTAGRAM}


def test_registry_installs_whatsapp_and_instagram_only() -> None:
    assert set(PLATFORMS) == INSTALLED
    assert set(BUILTIN_FIELDS) == INSTALLED
    assert set(RECORD_TYPES) == INSTALLED
    app = FastAPI()
    app.include_router(create_messaging_router())
    (param,) = (
        p
        for p in app.openapi()["paths"]["/api/{platform}/messages/send-text"]["post"][
            "parameters"
        ]
        if p["name"] == "platform"
    )
    assert {PlatformType(value) for value in param["schema"]["enum"]} == INSTALLED
    for platform, entry in PLATFORMS.items():
        assert entry.webhooks.platform is platform
        assert entry.webhooks.builtin_fields == BUILTIN_FIELDS[platform]


def test_each_app_table_binds_its_own_field_registry() -> None:
    class Insight(BaseModel):
        media_id: str

    async def handler(webhook: Any) -> None:
        return None

    registry = FieldHandlerRegistry(BUILTIN_FIELDS)
    registry.register(
        "story_insights",
        parser=Insight,
        handler=handler,
        platform=PlatformType.INSTAGRAM,
    )
    table = build_platforms(registry)
    assert table.keys() == PLATFORMS.keys()
    assert table[PlatformType.INSTAGRAM].webhooks is not (
        PLATFORMS[PlatformType.INSTAGRAM].webhooks
    )


def test_field_registry_rejects_an_uninstalled_platform() -> None:
    class Value(BaseModel):
        x: int

    async def handler(webhook: Any) -> None:
        return None

    registry = FieldHandlerRegistry(BUILTIN_FIELDS)
    with pytest.raises(ValueError, match="not available for telegram"):
        registry.register(
            "anything", parser=Value, handler=handler, platform=PlatformType.TELEGRAM
        )
    with pytest.raises(ValueError, match="built-in"):
        registry.register(
            "mentions", parser=Value, handler=handler, platform=PlatformType.INSTAGRAM
        )


async def test_messenger_factory_rejects_an_uninstalled_platform() -> None:
    factory = MessengerFactory(
        session_provider=lambda: httpx.AsyncClient(),
        media_download_client_provider=lambda: httpx.AsyncClient(),
    )
    inbox_ref = InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")
    credentials = ResolvedInboxCredentials(
        inbox_ref=inbox_ref,
        account_ref=PlatformAccountRef(
            platform=PlatformType.TELEGRAM, platform_account_id="acct"
        ),
        access_token=SecretStr("token"),
        credential_version=1,
    )
    with pytest.raises(ValueError, match="Unsupported platform: telegram"):
        await factory.create_messenger(inbox_ref, credentials=credentials)


def test_credential_service_picks_record_classes_from_record_types() -> None:
    service = InboxCredentialService(CredentialCodec(CredentialCodec.generate_key()))
    for platform, (active_type, inactive_type) in RECORD_TYPES.items():
        inbox_ref = InboxRef(platform=platform, inbox_id="1789")
        account_ref = PlatformAccountRef(platform=platform, platform_account_id="1789")
        active = service.create_active_record(
            inbox_ref=inbox_ref,
            account_ref=account_ref,
            access_token=SecretStr("token"),
        )
        assert type(active) is active_type
        assert type(service.create_inactive_record(active)) is inactive_type
        assert service.rotate_encrypted_record(active).access_token != (
            active.access_token
        )
    with pytest.raises(ValueError, match="implemented Platform"):
        service.create_active_record(
            inbox_ref=InboxRef(platform=PlatformType.TELEGRAM, inbox_id="1"),
            account_ref=PlatformAccountRef(
                platform=PlatformType.TELEGRAM, platform_account_id="1"
            ),
            access_token=SecretStr("token"),
        )


async def test_directory_health_probe_names_no_inbox() -> None:
    class _Table:
        context_id = "__system__"

        def __init__(self, fail: bool) -> None:
            self.fail = fail
            self.keys: list[str] = []

        async def get(self, table: str, key: str) -> None:
            self.keys.append(key)
            if self.fail:
                raise ConnectionError("down")

    healthy = _Table(fail=False)
    await InboxDirectoryTable(healthy).ping()  # type: ignore[arg-type]
    assert healthy.keys and "__" in healthy.keys[0]
    assert not healthy.keys[0].startswith(("whatsapp", "instagram"))
    with pytest.raises(InboxDirectoryUnavailableError):
        await InboxDirectoryTable(_Table(fail=True)).ping()  # type: ignore[arg-type]


def _inbox() -> InboxBase:
    return InboxBase(inbox_id="1789", display_address=None, platform_account_id="1789")


def test_sse_identity_reads_evidence_fields_not_the_platform() -> None:
    runtime = InboundRuntime.__new__(InboundRuntime)
    instagram = InboundMessageWebhook(
        inbox=_inbox(),
        user=UserBase(platform_user_id="igsid-1"),
        message=InstagramTextMessage(
            id="m1", sender="igsid-1", account_id="1789", timestamp_ms=1, text="hi"
        ),
        timestamp=datetime.now(UTC),
        platform=PlatformType.INSTAGRAM,
        webhook_id="m1",
    )
    assert runtime._derive_sse_identity(instagram, "igsid-1") == (
        "igsid-1",
        None,
        None,
    )

    status = StatusWebhook(
        inbox=_inbox(),
        message_id="wamid.1",
        status=MessageStatus.DELIVERED,
        recipient_phone_id="573001234567",
        recipient_bsuid="CO.abc123",
        timestamp=datetime.now(UTC),
        platform=PlatformType.WHATSAPP,
        webhook_id="s1",
    )
    assert runtime._derive_sse_identity(status, "CO.abc123") == (
        "CO.abc123",
        "CO.abc123",
        "573001234567",
    )

    instagram_read = StatusWebhook(
        inbox=_inbox(),
        message_id="m1",
        status=MessageStatus.READ,
        recipient_platform_id="igsid-1",
        timestamp=datetime.now(UTC),
        platform=PlatformType.INSTAGRAM,
        webhook_id="r1",
    )
    assert runtime._derive_sse_identity(instagram_read, "igsid-1") == (
        "igsid-1",
        None,
        None,
    )
