"""Two Inboxes on two Platforms in one app never share runtime scope.

A WhatsApp Inbox and an Instagram Inbox deliberately share the same raw
``inbox_id``. Identity is ``InboxRef(platform, inbox_id)``, so each Dispatch
Context, cache namespace, cached Messenger and SSE identity stays on its own
Platform.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import SecretStr

from wappa import WappaEventHandler
from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events import WappaEventDispatcher
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.inbound import SIGNATURE_HEADER, MetaCallbackAuthenticator
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.sse.context import get_sse_context
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.messaging.outbound_runtime import OutboundRuntime
from wappa.persistence.cache_factory import create_cache_factory
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import InboundMessageWebhook

SHARED_ID = "17841400000071"
WABA = "1111100000071"
WA_REF = InboxRef.whatsapp(SHARED_ID)
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=SHARED_ID)
APP_SECRET = SecretStr("two-platform-secret")
STATE_USER = "same-user-key"  # the same Host key on both Inboxes
PHONE = "573001112233"
BSUID = "CO.2186878922080771"


class Resolver(IInboxCredentialResolver):
    accounts = {
        WA_REF: PlatformAccountRef.whatsapp(WABA),
        IG_REF: PlatformAccountRef(
            platform=PlatformType.INSTAGRAM, platform_account_id=SHARED_ID
        ),
    }

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        if inbox_ref not in self.accounts:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=self.accounts[inbox_ref],
            access_token=SecretStr(f"token-{inbox_ref.platform.value}"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return tuple(ref for ref, acct in self.accounts.items() if acct == account_ref)


class Recorder(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[dict[str, Any]] = []

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        assert self.inbox_ref is not None and self.cache_factory is not None
        assert self.messenger is not None
        cache = self.cache_factory.create_user_cache(user_id=STATE_USER)
        before = await cache.get()
        await cache.upsert({"written_by": self.inbox_ref.platform.value})
        sse = get_sse_context()
        assert sse is not None
        self.seen.append(
            {
                "inbox_ref": self.inbox_ref,
                "namespace": self.cache_factory.inbox_id,
                "messenger_platform": self.messenger.platform,
                "state_before": before,
                "sse": (sse.platform, sse.bsuid, sse.phone_number),
            }
        )


def _whatsapp_payload() -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000071",
                                "phone_number_id": SHARED_ID,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": PHONE,
                                    "user_id": BSUID,
                                }
                            ],
                            "messages": [
                                {
                                    "from": PHONE,
                                    "from_user_id": BSUID,
                                    "id": "wamid.two-platform-1",
                                    "timestamp": "1776696189",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _instagram_payload() -> dict[str, Any]:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": SHARED_ID,
                "messaging": [
                    {
                        "sender": {"id": "6551596044932871"},
                        "recipient": {"id": SHARED_ID},
                        "timestamp": 1793710000123,
                        "message": {"mid": "ig.two-platform-1", "text": "hola"},
                    }
                ],
            }
        ],
    }


def _app(provider: httpx.AsyncClient, handler: Recorder) -> FastAPI:
    app = FastAPI()
    app.include_router(create_webhook_router(WappaEventDispatcher(handler)))
    app.state.meta_application_config = MetaApplicationConfig(
        app_secret=APP_SECRET, webhook_verify_token=SecretStr("verify")
    )
    app.state.session_lifecycle = SessionLifecycle(provider)
    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=InboxRoutingMode.EXPLICIT, credential_resolver=Resolver()
    )
    app.state.background_work_tracker = BackgroundWorkTracker()
    app.state.messenger_middleware = []
    app.state.wappa_cache_type = "memory"
    return app


async def _post(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> int:
    body = json.dumps(payload).encode()
    response = await client.post(
        path,
        content=body,
        headers={
            SIGNATURE_HEADER: MetaCallbackAuthenticator(APP_SECRET).sign(body),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200, response.text
    return response.status_code


async def test_same_raw_inbox_id_on_two_platforms_stays_isolated() -> None:
    handler = Recorder()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as provider:
        app = _app(provider, handler)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await _post(client, "/webhook/inboxes/whatsapp", _whatsapp_payload())
            await _post(client, "/webhook/inboxes/instagram", _instagram_payload())
            await app.state.background_work_tracker.drain()

        by_platform = {seen["inbox_ref"].platform: seen for seen in handler.seen}
        assert len(handler.seen) == len(by_platform) == 2
        whatsapp = by_platform[PlatformType.WHATSAPP]
        instagram = by_platform[PlatformType.INSTAGRAM]
        # Each Dispatch Context carries its own qualified Inbox.
        assert whatsapp["inbox_ref"] == WA_REF
        assert instagram["inbox_ref"] == IG_REF
        assert whatsapp["messenger_platform"] is PlatformType.WHATSAPP
        assert instagram["messenger_platform"] is PlatformType.INSTAGRAM
        # One cache namespace rule for every Platform (ADR-0022).
        assert whatsapp["namespace"] == f"whatsapp__{SHARED_ID}"
        assert instagram["namespace"] == f"instagram__{SHARED_ID}"
        # State the WhatsApp handler wrote is invisible to the Instagram one.
        assert whatsapp["state_before"] is None
        assert instagram["state_before"] is None
        memory = create_cache_factory("memory")
        for ref in (WA_REF, IG_REF):
            stored = (
                await memory(inbox_id=ref.cache_namespace, user_id=STATE_USER)
                .create_user_cache()
                .get()
            )
            assert stored is not None
            assert stored["written_by"] == ref.platform.value
        # SSE identity comes from each adapter's evidence.
        assert whatsapp["sse"] == ("whatsapp", BSUID, PHONE)
        assert instagram["sse"] == ("instagram", None, None)

        # Outbound: one cached Messenger per qualified Inbox.
        runtime = OutboundRuntime.from_app(app)
        wa_messenger = (await runtime.messenger(WA_REF)).raw_messenger
        ig_messenger = (await runtime.messenger(IG_REF)).raw_messenger
        assert wa_messenger is not ig_messenger
        assert wa_messenger.platform is PlatformType.WHATSAPP
        assert ig_messenger.platform is PlatformType.INSTAGRAM
        runtime.evict_inbox(WA_REF)
        assert (await runtime.messenger(WA_REF)).raw_messenger is not wa_messenger
        assert (await runtime.messenger(IG_REF)).raw_messenger is ig_messenger
        await app.state.session_lifecycle.close()
