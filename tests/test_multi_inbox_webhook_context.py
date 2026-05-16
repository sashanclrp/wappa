from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from wappa.api.controllers.webhook_controller import WebhookController
from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.core.events.event_handler import WappaEventHandler
from wappa.domain.interfaces.inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks import IncomingMessageWebhook

INBOX_1 = "111111111111111"
INBOX_2 = "222222222222222"


class _MultiInboxCredentialStore(IInboxCredentialStore):
    def __init__(self) -> None:
        self._credentials = {
            INBOX_1: InboxCredentials(
                inbox_id=INBOX_1,
                access_token="token-inbox-1",
                platform_account_id="1111111111",
            ),
            INBOX_2: InboxCredentials(
                inbox_id=INBOX_2,
                access_token="token-inbox-2",
                platform_account_id="2222222222",
            ),
        }
        self.lookups: list[str] = []

    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        self.lookups.append(inbox_id)
        credentials = self._credentials.get(inbox_id)
        if credentials is None:
            raise InboxNotFoundError(inbox_id)
        return credentials

    async def validate_inbox(self, inbox_id: str) -> bool:
        return inbox_id in self._credentials


class _RecordingHTTPSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        payload = json or data or {}
        self.posts.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "files": files,
            }
        )
        recipient = str(payload.get("recipient") or payload.get("to") or "")
        contact = {"input": recipient}
        if recipient.startswith("CO."):
            contact["user_id"] = recipient
        else:
            contact["wa_id"] = recipient

        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "messaging_product": "whatsapp",
                "contacts": [contact],
                "messages": [{"id": f"wamid.{len(self.posts)}"}],
            },
        )


class _RecordingHandler(WappaEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        assert self.inbox_id is not None
        assert self.user_id is not None
        assert self.messenger is not None
        assert self.cache_factory is not None

        state_cache = self.cache_factory.create_state_cache()
        await state_cache.upsert(
            "multi-inbox-context",
            {
                "handler_inbox_id": self.inbox_id,
                "webhook_inbox_id": webhook.inbox.inbox_id,
                "user_id": self.user_id,
            },
        )
        cached_state = await state_cache.get("multi-inbox-context")

        send_result = await self.messenger.send_text(
            text=f"reply from {self.inbox_id}",
            recipient=webhook.user.user_id,
        )

        self.records.append(
            {
                "handler_inbox_id": self.inbox_id,
                "handler_user_id": self.user_id,
                "webhook_inbox_id": webhook.inbox.inbox_id,
                "webhook_user_id": webhook.user.user_id,
                "cache_inbox_id": state_cache.inbox,
                "cache_user_id": state_cache.user_id,
                "cached_state": cached_state,
                "messenger_inbox_id": self.messenger.inbox_id,
                "send_result_inbox_id": send_result.inbox_id,
                "send_result_recipient": send_result.recipient,
            }
        )


def _message_payload(
    *,
    inbox_id: str,
    platform_account_id: str,
    user_id: str,
    phone_number: str,
    message_id: str,
    text: str,
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": platform_account_id,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": inbox_id,
                            },
                            "contacts": [
                                {
                                    "wa_id": phone_number,
                                    "user_id": user_id,
                                    "profile": {"name": f"User {user_id}"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": phone_number,
                                    "from_user_id": user_id,
                                    "id": message_id,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_webhooks_from_multiple_inboxes_get_isolated_handler_contexts() -> None:
    handler = _RecordingHandler()
    controller = WebhookController(WappaEventDispatcher(handler))
    credential_store = _MultiInboxCredentialStore()
    http_session = _RecordingHTTPSession()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                http_session=http_session,
                inbox_credential_store=credential_store,
                messenger_middleware=[],
                wappa_cache_type="memory",
            )
        )
    )

    await controller._process_webhook_async(
        request=request,
        platform_type=PlatformType.WHATSAPP,
        inbox_id=INBOX_1,
        payload=_message_payload(
            inbox_id=INBOX_1,
            platform_account_id="1111111111",
            user_id="CO.USER111",
            phone_number="573001111111",
            message_id="wamid.inbox1",
            text="hello inbox 1",
        ),
    )
    await controller._process_webhook_async(
        request=request,
        platform_type=PlatformType.WHATSAPP,
        inbox_id=INBOX_2,
        payload=_message_payload(
            inbox_id=INBOX_2,
            platform_account_id="2222222222",
            user_id="CO.USER222",
            phone_number="573002222222",
            message_id="wamid.inbox2",
            text="hello inbox 2",
        ),
    )

    assert handler.records == [
        {
            "handler_inbox_id": INBOX_1,
            "handler_user_id": "CO.USER111",
            "webhook_inbox_id": INBOX_1,
            "webhook_user_id": "CO.USER111",
            "cache_inbox_id": INBOX_1,
            "cache_user_id": "CO.USER111",
            "cached_state": {
                "handler_inbox_id": INBOX_1,
                "webhook_inbox_id": INBOX_1,
                "user_id": "CO.USER111",
            },
            "messenger_inbox_id": INBOX_1,
            "send_result_inbox_id": INBOX_1,
            "send_result_recipient": "CO.USER111",
        },
        {
            "handler_inbox_id": INBOX_2,
            "handler_user_id": "CO.USER222",
            "webhook_inbox_id": INBOX_2,
            "webhook_user_id": "CO.USER222",
            "cache_inbox_id": INBOX_2,
            "cache_user_id": "CO.USER222",
            "cached_state": {
                "handler_inbox_id": INBOX_2,
                "webhook_inbox_id": INBOX_2,
                "user_id": "CO.USER222",
            },
            "messenger_inbox_id": INBOX_2,
            "send_result_inbox_id": INBOX_2,
            "send_result_recipient": "CO.USER222",
        },
    ]

    assert [post["url"].rsplit("/", 2)[-2:] for post in http_session.posts] == [
        [INBOX_1, "messages"],
        [INBOX_2, "messages"],
    ]
    assert [post["headers"]["Authorization"] for post in http_session.posts] == [
        "Bearer token-inbox-1",
        "Bearer token-inbox-2",
    ]
    assert [post["payload"]["recipient"] for post in http_session.posts] == [
        "CO.USER111",
        "CO.USER222",
    ]
