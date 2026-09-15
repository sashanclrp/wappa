"""Authentication Template OTP button contract.

Meta rewrites an ``OTP`` button to a ``URL`` button at template creation, so
every authentication method — ``copy_code``, ``one_tap``, ``zero_tap`` — sends
the same two components: the body the person reads, and a
``sub_type: "url"`` button whose single parameter fills the ``code=otp{{1}}``
placeholder in the button's URL. Omitting the button leaves a declared
placeholder unsupplied and Meta rejects the whole send.

These tests assert the emitted payload, not that the call succeeded: the
previous body-only defect survived precisely because nothing asserted what went
on the wire.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from wappa.messaging import (
    BsuidTemplateRecipient,
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    PhoneNumberTemplateRecipient,
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateMediaType,
    TemplateTransportLocationHeader,
    TemplateTransportMediaHeader,
    TemplateTransportParameter,
    TextTemplateTransportRequest,
)
from wappa.messaging.template_transport import _request_digest, _send_request
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.template_info_models import TemplateInfo
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    TemplateParameterType,
    WhatsAppTemplateType,
)

CODE = "ABC234"


class _UrlBuilder:
    def get_marketing_messages_url(self) -> str:  # pragma: no cover - unused here
        return "https://graph.facebook.com/v26.0/inbox-1/marketing_messages"


class _Client:
    def __init__(self) -> None:
        self.url_builder = _UrlBuilder()
        self.calls: list[tuple[dict[str, Any], str | None]] = []

    async def post_request(
        self, payload: dict[str, Any], custom_url: str | None = None
    ) -> dict[str, Any]:
        self.calls.append((payload, custom_url))
        return {
            "messages": [{"id": "wamid.otp"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


def _handler() -> tuple[WhatsAppTemplateHandler, _Client]:
    client = _Client()
    return WhatsAppTemplateHandler(client=client, inbox_id="inbox-1"), client


def _auth_request(**overrides: Any) -> TextTemplateTransportRequest:
    values: dict[str, Any] = {
        "recipient": PhoneNumberTemplateRecipient(value="573001112233"),
        "template_name": "otp_test_code",
        "category": TemplateCategory.AUTHENTICATION,
        "authentication_method": TemplateAuthenticationMethod.COPY_CODE,
        "language_code": "es_CO",
        "body_parameters": (TemplateTransportParameter(text=CODE),),
    }
    values.update(overrides)
    return TextTemplateTransportRequest(**values)


# --------------------------------------------------------------------------- #
# Emitted payload.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("method", list(TemplateAuthenticationMethod))
async def test_authentication_send_emits_body_and_otp_button(
    method: TemplateAuthenticationMethod,
) -> None:
    handler, client = _handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=[TemplateParameter(type=TemplateParameterType.TEXT, text=CODE)],
        language_code="es_CO",
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method=method.value,
    )

    assert result.success is True
    payload, custom_url = client.calls[0]
    assert custom_url is None  # authentication routes to /messages
    assert payload["template"]["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": CODE}]},
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": CODE}],
        },
    ]


@pytest.mark.asyncio
async def test_otp_button_index_is_a_string_not_an_integer() -> None:
    handler, client = _handler()

    await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=[TemplateParameter(type=TemplateParameterType.TEXT, text=CODE)],
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method="copy_code",
    )

    button = client.calls[0][0]["template"]["components"][1]
    assert button["index"] == "0"
    assert isinstance(button["index"], str)


@pytest.mark.asyncio
async def test_button_index_is_expressible_for_multi_button_templates() -> None:
    handler, client = _handler()

    await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=[TemplateParameter(type=TemplateParameterType.TEXT, text=CODE)],
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method="zero_tap",
        authentication_button_index=1,
    )

    assert client.calls[0][0]["template"]["components"][1]["index"] == "1"


@pytest.mark.asyncio
async def test_non_authentication_templates_emit_no_button() -> None:
    handler, client = _handler()

    await handler.send_text_template(
        recipient="573001112233",
        template_name="welcome",
        body_parameters=[
            TemplateParameter(type=TemplateParameterType.TEXT, text="Sasha")
        ],
        template_type=WhatsAppTemplateType.UTILITY,
    )

    components = client.calls[0][0]["template"]["components"]
    assert [component["type"] for component in components] == ["body"]


# --------------------------------------------------------------------------- #
# The method provably changes the outgoing request.
# --------------------------------------------------------------------------- #


class _RecordingMessenger:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def send_text_template(self, **values: Any) -> MessageResult:
        self.values = values
        return MessageResult(
            success=True,
            message_id="wamid.otp",
            recipient="573001112233",
            platform="whatsapp",
            inbox_id="inbox-1",
        )


@pytest.mark.asyncio
async def test_transport_carries_authentication_method_into_the_send() -> None:
    messenger = _RecordingMessenger()

    await _send_request(messenger, _auth_request())  # type: ignore[arg-type]

    # The field is required of every caller; this proves it is not discarded.
    assert messenger.values["authentication_method"] == "copy_code"
    assert messenger.values["authentication_button_index"] == 0
    assert messenger.values["template_type"] == "authentication"


@pytest.mark.asyncio
async def test_transport_sends_no_authentication_method_for_other_categories() -> None:
    messenger = _RecordingMessenger()

    await _send_request(  # type: ignore[arg-type]
        messenger,
        TextTemplateTransportRequest(
            recipient=PhoneNumberTemplateRecipient(value="573001112233"),
            template_name="welcome",
            category=TemplateCategory.UTILITY,
            body_parameters=(TemplateTransportParameter(text="Sasha"),),
        ),
    )

    assert messenger.values["authentication_method"] is None


# --------------------------------------------------------------------------- #
# Idempotency: a resend with a fresh PIN is never a replay of the last one.
# --------------------------------------------------------------------------- #


def test_request_digest_distinguishes_two_codes() -> None:
    first = _auth_request()
    second = _auth_request(body_parameters=(TemplateTransportParameter(text="ZZZ999"),))

    assert _request_digest(first) != _request_digest(second)
    assert _request_digest(first) == _request_digest(_auth_request())


def test_request_digest_distinguishes_two_authentication_methods() -> None:
    copy_code = _auth_request()
    one_tap = _auth_request(authentication_method=TemplateAuthenticationMethod.ONE_TAP)

    assert _request_digest(copy_code) != _request_digest(one_tap)


# --------------------------------------------------------------------------- #
# Local refusals: cheaper than a provider round trip.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "body_parameters",
    [
        pytest.param((), id="no-code"),
        pytest.param(
            (
                TemplateTransportParameter(text=CODE),
                TemplateTransportParameter(text="extra"),
            ),
            id="two-parameters",
        ),
    ],
)
def test_authentication_request_requires_exactly_one_body_parameter(
    body_parameters: tuple[TemplateTransportParameter, ...],
) -> None:
    with pytest.raises(ValidationError, match="exactly one body parameter"):
        _auth_request(body_parameters=body_parameters)


def test_authentication_request_rejects_named_parameters() -> None:
    with pytest.raises(ValidationError, match="cannot bind a named parameter"):
        _auth_request(
            body_parameters=(
                TemplateTransportParameter(text=CODE, parameter_name="code"),
            )
        )


def test_authentication_request_still_rejects_bsuid_recipients() -> None:
    with pytest.raises(ValidationError, match="cannot use a BSUID recipient"):
        _auth_request(recipient=BsuidTemplateRecipient(value="CO.2186878922080769"))


def test_button_index_is_rejected_for_non_authentication_templates() -> None:
    with pytest.raises(ValidationError, match="only valid for authentication"):
        TextTemplateTransportRequest(
            recipient=PhoneNumberTemplateRecipient(value="573001112233"),
            template_name="welcome",
            category=TemplateCategory.UTILITY,
            authentication_button_index=1,
        )


def test_authentication_templates_reject_a_media_header() -> None:
    with pytest.raises(ValidationError, match="cannot carry a media header"):
        MediaTemplateTransportRequest(
            recipient=PhoneNumberTemplateRecipient(value="573001112233"),
            template_name="otp_test_code",
            category=TemplateCategory.AUTHENTICATION,
            authentication_method=TemplateAuthenticationMethod.COPY_CODE,
            body_parameters=(TemplateTransportParameter(text=CODE),),
            media_header=TemplateTransportMediaHeader(
                media_type=TemplateMediaType.IMAGE, media_id="media-1"
            ),
        )


def test_authentication_templates_reject_a_location_header() -> None:
    with pytest.raises(ValidationError, match="cannot carry a location header"):
        LocationTemplateTransportRequest(
            recipient=PhoneNumberTemplateRecipient(value="573001112233"),
            template_name="otp_test_code",
            category=TemplateCategory.AUTHENTICATION,
            authentication_method=TemplateAuthenticationMethod.COPY_CODE,
            body_parameters=(TemplateTransportParameter(text=CODE),),
            location_header=TemplateTransportLocationHeader(
                latitude="4.65", longitude="-74.05", name="Office", address="Bogota"
            ),
        )


# --------------------------------------------------------------------------- #
# Handler-level refusals, for callers that reach the adapter directly.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handler_refuses_authentication_send_without_a_method() -> None:
    handler, client = _handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=[TemplateParameter(type=TemplateParameterType.TEXT, text=CODE)],
        template_type=WhatsAppTemplateType.AUTHENTICATION,
    )

    assert result.success is False
    assert client.calls == []


@pytest.mark.asyncio
async def test_handler_refuses_a_method_on_a_non_authentication_template() -> None:
    handler, client = _handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="welcome",
        body_parameters=[
            TemplateParameter(type=TemplateParameterType.TEXT, text="Sasha")
        ],
        template_type=WhatsAppTemplateType.UTILITY,
        authentication_method="copy_code",
    )

    assert result.success is False
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_parameters",
    [
        pytest.param(None, id="no-code"),
        pytest.param(
            [
                TemplateParameter(type=TemplateParameterType.TEXT, text=CODE),
                TemplateParameter(type=TemplateParameterType.TEXT, text="extra"),
            ],
            id="two-parameters",
        ),
    ],
)
async def test_handler_refuses_a_malformed_authentication_body(
    body_parameters: list[TemplateParameter] | None,
) -> None:
    handler, client = _handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=body_parameters,
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method="copy_code",
    )

    assert result.success is False
    assert client.calls == []


@pytest.mark.asyncio
async def test_handler_refuses_an_unknown_authentication_method() -> None:
    handler, client = _handler()

    result = await handler.send_text_template(
        recipient="573001112233",
        template_name="otp_test_code",
        body_parameters=[TemplateParameter(type=TemplateParameterType.TEXT, text=CODE)],
        template_type=WhatsAppTemplateType.AUTHENTICATION,
        authentication_method="two_tap",
    )

    assert result.success is False
    assert client.calls == []


# --------------------------------------------------------------------------- #
# Resolving the method from the approved template itself.
# --------------------------------------------------------------------------- #


def _template_info(**overrides: Any) -> TemplateInfo:
    values: dict[str, Any] = {
        "id": "1",
        "name": "otp_test_code",
        "language": "es_CO",
        "status": "APPROVED",
        "category": "AUTHENTICATION",
        "components": [
            {"type": "BODY", "add_security_recommendation": True},
            {"type": "FOOTER", "code_expiration_minutes": 5},
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Copiar código",
                        "otp_type": None,
                        "url": (
                            "https://www.whatsapp.com/otp/code/"
                            "?otp_type=COPY_CODE&code_expiration_minutes=5"
                            "&code=otp{{1}}"
                        ),
                    }
                ],
            },
        ],
    }
    values.update(overrides)
    return TemplateInfo.model_validate(values)


def test_method_survives_a_null_otp_type_by_reading_the_button_url() -> None:
    # Meta rewrites the OTP button to type "URL" and returns otp_type null, so
    # the flat field alone resolves to nothing and the send gets rejected
    # before it is ever attempted.
    assert (
        _template_info().authentication_method is TemplateAuthenticationMethod.COPY_CODE
    )


@pytest.mark.parametrize(
    ("otp_type", "expected"),
    [
        ("COPY_CODE", TemplateAuthenticationMethod.COPY_CODE),
        ("ONE_TAP", TemplateAuthenticationMethod.ONE_TAP),
        ("ZERO_TAP", TemplateAuthenticationMethod.ZERO_TAP),
    ],
)
def test_method_is_read_from_a_populated_otp_type(
    otp_type: str, expected: TemplateAuthenticationMethod
) -> None:
    template = _template_info(
        components=[
            {
                "type": "BUTTONS",
                "buttons": [{"type": "URL", "text": "Copy", "otp_type": otp_type}],
            }
        ]
    )

    assert template.authentication_method is expected


def test_a_non_authentication_template_resolves_to_no_method() -> None:
    assert _template_info(category="UTILITY").authentication_method is None


def test_an_unmarked_url_button_resolves_to_no_method_rather_than_a_guess() -> None:
    template = _template_info(
        components=[
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Track order",
                        "url": "https://example.com/orders/{{1}}",
                    }
                ],
            }
        ]
    )

    assert template.authentication_method is None


def test_a_resolved_method_is_accepted_by_the_transport_request() -> None:
    # The end-to-end point of resolving it: read the approved template, then
    # send it without the caller hard-coding a method it cannot verify.
    method = _template_info().authentication_method
    assert method is not None

    request = _auth_request(authentication_method=method)

    assert request.authentication_method is TemplateAuthenticationMethod.COPY_CODE
    assert request.authentication_code == CODE
