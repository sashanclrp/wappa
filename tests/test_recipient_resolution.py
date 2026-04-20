import pytest

from wappa.api.models.handler_models import SetHandlerStateRequest
from wappa.api.routes.whatsapp.whatsapp_specialized import ContactRequest
from wappa.messaging.whatsapp.models.basic_models import BasicTextMessage
from wappa.messaging.whatsapp.models.media_models import ImageMessage
from wappa.schemas.core.recipient import (
    apply_recipient_to_payload,
    looks_like_bsuid,
    normalize_recipient_identifier,
    resolve_recipient,
)


def test_normalize_recipient_identifier_compacts_phone_numbers() -> None:
    assert normalize_recipient_identifier("+57 300 123 4567") == "+573001234567"


def test_normalize_recipient_identifier_normalizes_lowercase_bsuid() -> None:
    assert (
        normalize_recipient_identifier("co.13491208655302741918")
        == "CO.13491208655302741918"
    )


def test_resolve_recipient_routes_bsuid_to_recipient_field() -> None:
    resolved = resolve_recipient("us.13491208655302741918")

    assert resolved.transport_field == "recipient"
    assert resolved.transport_value == "US.13491208655302741918"
    assert looks_like_bsuid("us.13491208655302741918") is True


def test_apply_recipient_to_payload_replaces_conflicting_fields() -> None:
    payload = {"to": "+123", "recipient": "CO.old", "type": "text"}

    apply_recipient_to_payload(payload, "co.13491208655302741918")

    assert payload == {
        "recipient": "CO.13491208655302741918",
        "type": "text",
    }


def test_basic_text_message_canonicalizes_recipient() -> None:
    message = BasicTextMessage(text="hola", recipient="+57 300 123 4567")

    assert message.recipient == "+573001234567"


def test_image_message_canonicalizes_bsuid_recipient() -> None:
    message = ImageMessage(
        recipient="co.13491208655302741918",
        media_source="https://example.com/image.png",
    )

    assert message.recipient == "CO.13491208655302741918"


def test_handler_request_canonicalizes_recipient() -> None:
    request = SetHandlerStateRequest(
        recipient="co.13491208655302741918",
        handler_config={"handler_value": "flow", "ttl_seconds": 300},
    )

    assert request.recipient == "CO.13491208655302741918"


def test_specialized_route_request_canonicalizes_recipient() -> None:
    request = ContactRequest(
        recipient="co.13491208655302741918",
        contact={
            "name": {"formatted_name": "Demo User"},
            "phones": [{"phone": "+57 300 123 4567"}],
        },
    )

    assert request.recipient == "CO.13491208655302741918"


def test_invalid_recipient_is_rejected() -> None:
    with pytest.raises(ValueError, match="Recipient identifier must be"):
        normalize_recipient_identifier("not-a-recipient")
