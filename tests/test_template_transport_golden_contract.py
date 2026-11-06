"""Golden Meta v25.0 Template transport contracts checked on 2026-08-03.

Graph API v26.0 (released 2026-07-29) ships no Template / ``marketing_messages``
changes, so these v25.0-captured fixtures remain the authoritative contract even
though ``META_API_VERSION`` now defaults to v26.0. Re-capture the fixtures under
a new ``fixtures/meta/<version>/`` directory only when Meta actually changes the
payload shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wappa.domain.inbox import InboxRef
from wappa.domain.results import OperationOutcome
from wappa.messaging.meta.graph import GraphResponse, MetaGraphError, meta_error_code
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    TemplateParameterType,
    WhatsAppTemplateType,
)
from wappa.webhooks.whatsapp import WhatsAppMessageStatus, WhatsAppWebhook

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "meta" / "v25.0"
CONTRACT_GRAPH_API_VERSION = "v25.0"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text())


class _UrlBuilder:
    def get_marketing_messages_url(self) -> str:
        return "https://graph.facebook.com/v25.0/inbox-test/marketing_messages"


class _GoldenClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.url_builder = _UrlBuilder()
        self.response = response
        self.calls: list[tuple[dict[str, Any], str | None]] = []

    async def post_request(
        self, payload: dict[str, Any], custom_url: str | None = None
    ) -> dict[str, Any]:
        self.calls.append((payload, custom_url))
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("recipient", "template_type", "request_fixture", "uses_marketing_endpoint"),
    [
        (
            "573001112233",
            WhatsAppTemplateType.UTILITY,
            "messages_phone_request.json",
            False,
        ),
        (
            "CO.2186878922080769",
            WhatsAppTemplateType.MARKETING,
            "marketing_bsuid_request.json",
            True,
        ),
    ],
)
async def test_golden_template_requests(
    recipient: str,
    template_type: WhatsAppTemplateType,
    request_fixture: str,
    uses_marketing_endpoint: bool,
) -> None:
    client = _GoldenClient(_fixture("template_accepted_response.json"))
    handler = WhatsAppMessengerAdapter(
        client=client, media_transport=None, inbox_id="inbox-test"
    )

    result = await handler._send_text_template_to(
        recipient=recipient,
        template_name=_fixture(request_fixture)["template"]["name"],
        template_type=template_type,
    )

    payload, custom_url = client.calls[0]
    assert payload == _fixture(request_fixture)
    assert bool(custom_url) is uses_marketing_endpoint
    assert result.message_id == "wamid.golden"
    assert result.recipient_phone == "573001112233"
    assert result.recipient_bsuid == "CO.2186878922080769"
    assert result.recipient_parent_bsuid == "CO.ENT.2186878922080769"
    assert result.recipient_username == "known_customer"


@pytest.mark.asyncio
async def test_golden_authentication_copy_code_request() -> None:
    """The exact two-component payload Meta documents for an OTP template.

    Meta rewrites the ``OTP`` button to a ``URL`` button at creation, so the
    send repeats the body's code in a ``sub_type: "url"`` button parameter that
    fills the ``code=otp{{1}}`` placeholder in the button's URL.
    """
    client = _GoldenClient(_fixture("template_accepted_response.json"))
    handler = WhatsAppMessengerAdapter(
        client=client, media_transport=None, inbox_id="inbox-test"
    )
    expected = _fixture("authentication_copy_code_request.json")

    result = await handler._send_text_template_to(
        recipient="573001112233",
        template_name=expected["template"]["name"],
        body_parameters=[
            TemplateParameter(type=TemplateParameterType.TEXT, text="ABC234")
        ],
        language_code=expected["template"]["language"]["code"],
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method="copy_code",
    )

    payload, custom_url = client.calls[0]
    assert payload == expected
    assert custom_url is None
    assert result.message_id == "wamid.golden"


def test_golden_bsuid_error_keeps_stable_provider_code() -> None:
    body = _fixture("bsuid_unsupported_error.json")
    error = MetaGraphError(
        GraphResponse(
            outcome=OperationOutcome.REJECTED,
            status_code=400,
            body=body,
            error_code=meta_error_code(body),
            error="rejected",
        )
    )

    result = handle_whatsapp_error(
        error=error,
        operation="send Template",
        recipient="CO.2186878922080769",
        inbox_id="inbox-test",
        logger=__import__("logging").getLogger(__name__),
    )

    assert result.error_code == "BSUID_RECIPIENT_NOT_SUPPORTED"


def test_golden_status_webhook_preserves_identity_evidence() -> None:
    webhook = WhatsAppWebhook.model_validate(_fixture("template_status_webhook.json"))
    status = WhatsAppMessageStatus.model_validate(webhook.get_raw_statuses()[0])

    assert status.id == "wamid.golden"
    assert status.recipient_bsuid == "CO.2186878922080769"
    assert status.recipient_parent_bsuid == "CO.ENT.2186878922080769"


def test_golden_contract_names_active_graph_version() -> None:
    assert FIXTURE_DIR.name == CONTRACT_GRAPH_API_VERSION


@pytest.mark.asyncio
@pytest.mark.parametrize("phone", ["988391070925723", "573001112233"])
async def test_adapter_phone_evidence_reaches_template_transport(phone: str) -> None:
    from wappa.messaging import (
        InboxTemplateTransport,
        PhoneNumberTemplateRecipient,
        TemplateAddressKind,
        TemplateCategory,
        TemplateEndpoint,
        TemplateRoutingReason,
        TemplateTransportOutcome,
        TextTemplateTransportRequest,
    )

    # Synthetic contradiction, not a recovered production response.
    response = {
        "messaging_product": "whatsapp",
        "contacts": [
            {
                "input": "988391070925723",
                "wa_id": phone,
                "user_id": "CO.988391070925723",
                "parent_user_id": "CO.ENT.988391070925723",
                "username": "known_customer",
            }
        ],
        "messages": [{"id": "wamid.synthetic.identity-echo"}],
    }
    client = _GoldenClient(response)
    messenger = WhatsAppMessengerAdapter(
        client=client,
        media_transport=None,
        inbox_id="inbox-test",
    )

    async def provide_messenger():
        return messenger

    request = TextTemplateTransportRequest(
        recipient=PhoneNumberTemplateRecipient(value="988391070925723"),
        template_name="welcome",
        category=TemplateCategory.MARKETING,
    )
    transport = InboxTemplateTransport(
        inbox_ref=InboxRef.whatsapp("inbox-test"), messenger_provider=provide_messenger
    )
    result = await transport.send(request)

    expected_phone = None if phone == "988391070925723" else phone
    assert result.returned_phone_number == expected_phone
    assert result.model_dump()["returned_phone_number"] == expected_phone
    assert result.outcome is TemplateTransportOutcome.ACCEPTED
    assert result.requested_address_kind is TemplateAddressKind.PHONE_NUMBER
    assert result.requested_address == request.recipient.value
    assert result.selected_endpoint is TemplateEndpoint.MARKETING_MESSAGES
    assert result.routing_reason is TemplateRoutingReason.CATEGORY_DEFAULT
    assert result.platform_message_id == "wamid.synthetic.identity-echo"
    assert result.returned_bsuid == "CO.988391070925723"
    assert result.returned_parent_bsuid == "CO.ENT.988391070925723"
    assert result.returned_username == "known_customer"
    assert len(client.calls) == 1
    payload, custom_url = client.calls[0]
    assert payload["to"] == request.recipient.value
    assert custom_url == client.url_builder.get_marketing_messages_url()
    assert client.response == response
