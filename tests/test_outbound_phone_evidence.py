"""Outbound phone evidence must not repeat a corroborating BSUID's digits."""

import json

import pytest

from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.models.basic_models import (
    WhatsAppAPIResponse,
    message_result_from_api_response,
    message_result_from_payload,
)
from wappa.schemas.core.types import PlatformType

DIGITS = "988391070925723"


@pytest.mark.parametrize("construction", ["payload", "typed", "direct"])
@pytest.mark.parametrize(
    ("phone", "bsuid", "parent_bsuid", "recipient", "expected"),
    [
        (DIGITS, f"CO.{DIGITS}", None, None, None),
        (DIGITS, None, f"CO.ENT.{DIGITS}", None, None),
        (DIGITS, "CO.other", f"CO.ENT.{DIGITS}", None, None),
        (f" +{DIGITS} ", f" co.{DIGITS} ", None, None, None),
        (DIGITS, None, f" co.ent.{DIGITS} ", None, None),
        ("573001112233", f"CO.{DIGITS}", None, None, "573001112233"),
        (" +573001112233 ", f"CO.{DIGITS}", None, None, " +573001112233 "),
        (DIGITS, f"CO.A{DIGITS}", None, None, DIGITS),
        (DIGITS, f"ZZ.{DIGITS}", None, None, DIGITS),
        (DIGITS, f"CO.BAD.{DIGITS}", None, None, DIGITS),
        (DIGITS, f"CO.{DIGITS}0", None, None, DIGITS),
        (DIGITS, None, None, None, DIGITS),
        ("", f"CO.{DIGITS}", None, None, ""),
        (None, f"CO.{DIGITS}", None, None, None),
    ],
)
def test_phone_evidence_normalization(
    construction: str,
    phone: str | None,
    bsuid: str | None,
    parent_bsuid: str | None,
    recipient: str | None,
    expected: str | None,
) -> None:
    payload = {
        "contacts": [
            {
                "input": recipient or DIGITS,
                "wa_id": phone or "",
                "user_id": bsuid,
                "parent_user_id": parent_bsuid,
                "username": "known_customer",
            }
        ],
        "messages": [{"id": "wamid.synthetic.identity-echo"}],
    }
    if construction == "direct":
        result = MessageResult(
            success=True,
            platform=PlatformType.WHATSAPP,
            message_id="wamid.synthetic.identity-echo",
            recipient=recipient or bsuid or DIGITS,
            recipient_phone=phone,
            recipient_bsuid=bsuid,
            recipient_parent_bsuid=parent_bsuid,
            recipient_username="known_customer",
            inbox_id="inbox-test",
        )
    elif construction == "typed":
        response = WhatsAppAPIResponse.model_validate(payload)
        result = message_result_from_api_response(response, inbox_id="inbox-test")
        assert result.platform_response == response.model_dump(by_alias=True)
    else:
        result = message_result_from_payload(payload, inbox_id="inbox-test")
        assert result.platform_response == payload

    if construction != "direct":
        # Factories already normalize empty provider phones to unknown.
        expected = expected or None
        assert result.platform_response is not None
        native = WhatsAppAPIResponse.model_validate(result.platform_response)
        assert native.primary_contact is not None
        assert native.primary_contact.wa_id == (phone or "")
    assert result.recipient_phone == expected
    expected_recipient = recipient or bsuid or phone or DIGITS
    if construction != "direct" and bsuid:
        expected_recipient = bsuid.strip()
    assert result.recipient == expected_recipient
    assert result.recipient_bsuid == bsuid
    assert result.recipient_parent_bsuid == parent_bsuid
    assert result.recipient_username == "known_customer"
    assert result.success is True
    assert result.message_id == "wamid.synthetic.identity-echo"
    assert result.inbox_id == "inbox-test"
    assert result.platform == "whatsapp"
    assert result.error is None
    assert result.error_code is None
    assert result.model_dump()["recipient_phone"] == expected
    assert json.loads(result.model_dump_json())["recipient_phone"] == expected


@pytest.mark.parametrize("recipient", [f"CO.{DIGITS}", f"CO.ENT.{DIGITS}"])
def test_resolved_bsuid_recipient_also_excludes_echo(recipient: str) -> None:
    result = MessageResult(
        success=True,
        platform=PlatformType.WHATSAPP,
        recipient=recipient,
        recipient_phone=DIGITS,
    )
    assert result.recipient == recipient
    assert result.recipient_phone is None


def test_bsuid_input_without_user_id_remains_canonical() -> None:
    result = message_result_from_payload(
        {
            "contacts": [{"input": f"CO.{DIGITS}", "wa_id": ""}],
            "messages": [{"id": "wamid.input-only"}],
        }
    )
    assert result.recipient == f"CO.{DIGITS}"
    assert result.recipient_phone is None


def test_error_semantics_survive_phone_normalization() -> None:
    result = message_result_from_api_response(
        WhatsAppAPIResponse.model_validate(
            {
                "contacts": [
                    {"input": DIGITS, "wa_id": DIGITS, "user_id": f"CO.{DIGITS}"}
                ],
            }
        ),
        success=False,
        error="rejected",
        error_code="131026",
    )
    assert result.recipient_phone is None
    assert result.success is False
    assert result.error == "rejected"
    assert result.error_code == "131026"


def test_unrelated_contacts_and_requested_address_are_not_corroboration() -> None:
    result = message_result_from_payload(
        {
            "contacts": [
                {"input": DIGITS, "wa_id": DIGITS},
                {"input": f"CO.{DIGITS}", "user_id": f"CO.{DIGITS}"},
            ],
            "messages": [{"id": "wamid.primary-only"}],
        },
        fallback_recipient=f"CO.{DIGITS}",
    )
    assert result.recipient == DIGITS
    assert result.recipient_phone == DIGITS


def test_message_result_requires_a_platform() -> None:
    with pytest.raises(ValueError):
        MessageResult(success=True)  # type: ignore[call-arg]


def test_platform_response_is_not_serialized() -> None:
    result = message_result_from_payload(
        {"contacts": [], "messages": [{"id": "wamid.native"}]}
    )
    assert "platform_response" not in result.model_dump()
    assert "api_response" not in result.model_dump()
