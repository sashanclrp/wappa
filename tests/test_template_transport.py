"""Contract tests for the public Inbox-scoped Template transport."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from wappa.api.routes.whatsapp_combined import create_whatsapp_router
from wappa.domain.interfaces.session_provider import RuntimeDrainingError
from wappa.messaging import (
    BsuidTemplateRecipient,
    InboxTemplateTransport,
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    PhoneNumberTemplateRecipient,
    TemplateAddressKind,
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateEndpoint,
    TemplateMediaType,
    TemplateRoutingPolicy,
    TemplateRoutingReason,
    TemplateTransportLocationHeader,
    TemplateTransportMediaHeader,
    TemplateTransportOutcome,
    TemplateTransportParameter,
    TemplateTransportResult,
    TemplateTransportRouting,
    TextTemplateTransportRequest,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult


def _text_request(**overrides: Any) -> TextTemplateTransportRequest:
    values = {
        "recipient": PhoneNumberTemplateRecipient(value="573001112233"),
        "template_name": "welcome",
        "category": TemplateCategory.UTILITY,
        "body_parameters": (TemplateTransportParameter(text="Sasha"),),
    }
    values.update(overrides)
    return TextTemplateTransportRequest(**values)


class _Runtime:
    def __init__(self, messenger: object | None = None, error: Exception | None = None):
        self.messenger = messenger
        self.error = error
        self.credentials_seen: list[Any] = []

    async def _messenger(self, inbox_id: str, *, credentials: Any = None):
        assert inbox_id == "inbox-1"
        # Record what the transport forwarded so a caller-supplied record is
        # visibly reused instead of forcing a second directory lookup.
        self.credentials_seen.append(credentials)
        if self.error:
            raise self.error
        return self.messenger


class _Messenger:
    def __init__(self, result: MessageResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _call(self, kind: str, values: dict[str, Any]) -> MessageResult:
        self.calls.append((kind, values))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def send_text_template(self, **values: Any) -> MessageResult:
        return await self._call("text", values)

    async def send_media_template(self, **values: Any) -> MessageResult:
        return await self._call("media", values)

    async def send_location_template(self, **values: Any) -> MessageResult:
        return await self._call("location", values)


def _transport(runtime: _Runtime) -> InboxTemplateTransport:
    return InboxTemplateTransport(runtime=runtime, inbox_id="inbox-1")  # type: ignore[arg-type]


def test_transport_request_forbids_host_application_fields() -> None:
    forbidden = (
        "state_config",
        "template_metadata",
        "agent_id",
        "campaign_id",
        "authority",
        "conversation_focus",
        "reply_state",
        "metadata",
    )
    for field in forbidden:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _text_request(**{field: "forbidden"})


def test_accepted_result_requires_platform_message_id() -> None:
    with pytest.raises(ValidationError, match="requires a platform Message ID"):
        TemplateTransportResult(
            outcome=TemplateTransportOutcome.ACCEPTED,
            inbox_id="inbox-1",
            requested_address_kind=TemplateAddressKind.PHONE_NUMBER,
            requested_address="573001112233",
            selected_endpoint=TemplateEndpoint.MESSAGES,
            routing_reason=TemplateRoutingReason.CATEGORY_DEFAULT,
            request_digest="sha256:example",
            platform_latency_ms=1,
        )


@pytest.mark.asyncio
async def test_text_transport_returns_normalized_acceptance_and_exact_mapping() -> None:
    messenger = _Messenger(
        MessageResult(
            success=True,
            message_id="wamid.1",
            recipient="CO.user",
            recipient_bsuid="CO.user",
            recipient_phone="573001112233",
            recipient_parent_bsuid="CO.ENT.user",
            recipient_username="sasha",
            inbox_id="inbox-1",
        )
    )
    result = await _transport(_Runtime(messenger)).send(_text_request())

    assert result.outcome is TemplateTransportOutcome.ACCEPTED
    assert result.platform_message_id == "wamid.1"
    assert result.resolved_recipient_id == "CO.user"
    assert result.requested_address_kind.value == "phone_number"
    assert result.requested_address == "573001112233"
    assert result.returned_phone_number == "573001112233"
    assert result.returned_bsuid == "CO.user"
    assert result.returned_parent_bsuid == "CO.ENT.user"
    assert result.returned_username == "sasha"
    assert result.selected_endpoint is TemplateEndpoint.MESSAGES
    assert result.routing_reason is TemplateRoutingReason.CATEGORY_DEFAULT
    assert result.inbox_id == "inbox-1"
    assert result.request_digest.startswith("sha256:")
    assert result.platform_latency_ms >= 0
    assert messenger.calls == [
        (
            "text",
            {
                "template_name": "welcome",
                "recipient": "573001112233",
                "body_parameters": [{"type": "text", "text": "Sasha"}],
                "language_code": "es",
                "template_type": "utility",
                "routing_policy": "category_default",
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template_request", "kind", "header_values"),
    [
        (
            MediaTemplateTransportRequest(
                recipient=PhoneNumberTemplateRecipient(value="573001112233"),
                template_name="brochure",
                category=TemplateCategory.MARKETING,
                media_header=TemplateTransportMediaHeader(
                    media_type=TemplateMediaType.DOCUMENT,
                    media_url="https://cdn.example.com/file.pdf",
                ),
            ),
            "media",
            {
                "media_type": "document",
                "media_id": None,
                "media_url": "https://cdn.example.com/file.pdf",
            },
        ),
        (
            LocationTemplateTransportRequest(
                recipient=PhoneNumberTemplateRecipient(value="573001112233"),
                template_name="store",
                category=TemplateCategory.UTILITY,
                location_header=TemplateTransportLocationHeader(
                    latitude="4.6097",
                    longitude="-74.0817",
                    name="HQ",
                    address="Bogota",
                ),
            ),
            "location",
            {
                "latitude": "4.6097",
                "longitude": "-74.0817",
                "name": "HQ",
                "address": "Bogota",
            },
        ),
    ],
)
async def test_header_template_requests_map_to_the_matching_pipeline_method(
    template_request: MediaTemplateTransportRequest | LocationTemplateTransportRequest,
    kind: str,
    header_values: dict[str, Any],
) -> None:
    messenger = _Messenger(MessageResult(success=True, message_id="wamid.2"))
    result = await _transport(_Runtime(messenger)).send(template_request)

    assert result.outcome is TemplateTransportOutcome.ACCEPTED
    assert messenger.calls[0][0] == kind
    assert header_values.items() <= messenger.calls[0][1].items()


@pytest.mark.asyncio
async def test_success_without_message_identity_is_indeterminate() -> None:
    result = await _transport(
        _Runtime(_Messenger(MessageResult(success=True, recipient="573001112233")))
    ).send(_text_request())

    assert result.outcome is TemplateTransportOutcome.INDETERMINATE
    assert result.error_code == "accepted_without_platform_message_id"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_result", "outcome"),
    [
        (
            MessageResult(
                success=False,
                error_code="131026",
                error="raw response must not escape",
            ),
            TemplateTransportOutcome.REJECTED,
        ),
        (
            MessageResult(
                success=False,
                error_code="platform_outcome_indeterminate",
                error="Bearer secret-token",
            ),
            TemplateTransportOutcome.INDETERMINATE,
        ),
        (
            MessageResult(
                success=False,
                error_code="runtime_unavailable",
                error="closed session detail",
            ),
            TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
        ),
    ],
)
async def test_failure_outcomes_are_distinct_and_redacted(
    message_result: MessageResult,
    outcome: TemplateTransportOutcome,
) -> None:
    result = await _transport(_Runtime(_Messenger(message_result))).send(
        _text_request()
    )

    assert result.outcome is outcome
    assert "secret" not in (result.error_message or "")
    assert "raw response" not in (result.error_message or "")


@pytest.mark.asyncio
async def test_drain_rejects_before_pipeline_execution() -> None:
    result = await _transport(
        _Runtime(error=RuntimeDrainingError("draining secret"))
    ).send(_text_request())

    assert result.outcome is TemplateTransportOutcome.TRANSPORT_UNAVAILABLE
    assert result.error_code == "runtime_unavailable"


@pytest.mark.asyncio
async def test_unexpected_pipeline_exception_is_indeterminate() -> None:
    result = await _transport(
        _Runtime(_Messenger(RuntimeError("unknown secret")))
    ).send(_text_request())

    assert result.outcome is TemplateTransportOutcome.INDETERMINATE
    assert result.error_code == "platform_outcome_indeterminate"
    assert "secret" not in (result.error_message or "")


@pytest.mark.parametrize(
    ("recipient", "normalized"),
    [
        (BsuidTemplateRecipient(value="co.user123"), "CO.user123"),
        (BsuidTemplateRecipient(value="co.ent.user123"), "CO.ENT.user123"),
        (PhoneNumberTemplateRecipient(value="+57 300-111-2233"), "+573001112233"),
    ],
)
def test_recipient_address_is_explicit_and_normalized(
    recipient: BsuidTemplateRecipient | PhoneNumberTemplateRecipient,
    normalized: str,
) -> None:
    assert recipient.value == normalized


@pytest.mark.parametrize(
    ("recipient_type", "value"),
    [
        (PhoneNumberTemplateRecipient, "CO.user123"),
        (BsuidTemplateRecipient, "573001112233"),
        (BsuidTemplateRecipient, "@sasha"),
    ],
)
def test_recipient_address_rejects_cross_shape_and_username(
    recipient_type: type[BsuidTemplateRecipient] | type[PhoneNumberTemplateRecipient],
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        recipient_type(value=value)


@pytest.mark.parametrize("method", list(TemplateAuthenticationMethod))
def test_authentication_templates_reject_bsuid_recipients(
    method: TemplateAuthenticationMethod,
) -> None:
    with pytest.raises(ValidationError, match="cannot use a BSUID"):
        _text_request(
            recipient=BsuidTemplateRecipient(value="CO.user123"),
            category=TemplateCategory.AUTHENTICATION,
            authentication_method=method,
        )


@pytest.mark.asyncio
async def test_marketing_fallback_is_explicit_and_recorded() -> None:
    messenger = _Messenger(MessageResult(success=True, message_id="wamid.fallback"))
    request = _text_request(
        category=TemplateCategory.MARKETING,
        routing=TemplateTransportRouting(
            policy=TemplateRoutingPolicy.CLOUD_MESSAGES_FALLBACK
        ),
    )

    result = await _transport(_Runtime(messenger)).send(request)

    assert result.selected_endpoint is TemplateEndpoint.MESSAGES
    assert result.routing_reason is TemplateRoutingReason.EXPLICIT_MARKETING_FALLBACK
    assert messenger.calls[0][1]["routing_policy"] == "cloud_messages_fallback"


def test_template_routes_require_explicit_capability_and_mount_once() -> None:
    default_app = FastAPI()
    default_app.include_router(create_whatsapp_router())
    enabled_app = FastAPI()
    enabled_app.include_router(create_whatsapp_router(include_template_transport=True))
    default_paths = tuple(default_app.openapi()["paths"])
    enabled_paths = tuple(enabled_app.openapi()["paths"])

    assert not any("/templates/send-" in path for path in default_paths)
    for suffix in ("text", "media", "location"):
        assert enabled_paths.count(f"/api/whatsapp/templates/send-{suffix}") == 1


@pytest.mark.asyncio
async def test_transport_reuses_credentials_the_caller_already_resolved() -> None:
    """A route holding an InboxExecutionContext must not make the directory answer twice."""
    messenger = _Messenger(MessageResult(success=True, message_id="wamid.reuse"))
    runtime = _Runtime(messenger)
    resolved = object()

    transport = InboxTemplateTransport(
        runtime=runtime,  # type: ignore[arg-type]
        inbox_id="inbox-1",
        credentials=resolved,  # type: ignore[arg-type]
    )
    result = await transport.send(_text_request())

    assert result.outcome is TemplateTransportOutcome.ACCEPTED
    assert runtime.credentials_seen == [resolved]


@pytest.mark.asyncio
async def test_transport_without_caller_credentials_resolves_through_the_runtime() -> (
    None
):
    """Non-HTTP callers pass nothing and let the runtime resolve the Inbox itself."""
    messenger = _Messenger(MessageResult(success=True, message_id="wamid.noreuse"))
    runtime = _Runtime(messenger)

    transport = InboxTemplateTransport(runtime=runtime, inbox_id="inbox-1")  # type: ignore[arg-type]
    result = await transport.send(_text_request())

    assert result.outcome is TemplateTransportOutcome.ACCEPTED
    assert runtime.credentials_seen == [None]
