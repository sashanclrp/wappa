"""Release 0.34.6: shared representations and adapter-owned evidence."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from test_delivery_addresses import BSUID, PHONE, WA, _Client, _wa
from test_instagram_conversations import CDN, messaging, msg, parse
from test_message_parts import instagram_send
from test_platform_messaging_api import _app

from wappa import MetaApplicationConfig
from wappa.core.sse.context import classify_meta_identifier, sse_event_scope
from wappa.core.sse.event_hub import SSEEventHub
from wappa.core.sse.handlers import _normalized_webhook_payload, publish_api_sse_event
from wappa.domain.error_evidence import ErrorCategory, meta_error_evidence
from wappa.domain.events.api_message_event import APIMessageEvent
from wappa.domain.inbox import InboxRef, PlatformAccountRef
from wappa.domain.message_parts import message_part, with_message_parts
from wappa.domain.results import MessageResult, aggregate_message_outcome
from wappa.domain.user_profile import PlatformUserProfile
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.messaging.meta.graph import GraphResponse, MetaGraphError
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.schemas.core.types import PlatformType
from wappa.schemas.requests.basic_models import BasicTextMessage, ReadStatusMessage
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase
from wappa.webhooks.whatsapp.message_types.context import WhatsAppMessageContext
from wappa.webhooks.whatsapp.models.base import MessageContext
from wappa.webhooks.whatsapp.processor import WhatsAppWebhookProcessor


@pytest.mark.parametrize("platform", [PlatformType.WHATSAPP, PlatformType.INSTAGRAM])
def test_identity_factories_match_generic_constructors(platform):
    assert getattr(InboxRef, platform.value)("account") == InboxRef(
        platform=platform, inbox_id="account"
    )
    assert getattr(PlatformAccountRef, platform.value)("account") == PlatformAccountRef(
        platform=platform, platform_account_id="account"
    )


@pytest.mark.parametrize(
    "address", ["ig:opaque", "12", "CO.ENT.123", "+57 300 123 4567"]
)
def test_shared_http_requests_preserve_opaque_addresses(address):
    request = BasicTextMessage(recipient=address, addresses=[address], text="hello")
    assert request.recipient == request.addresses[0] == address
    assert ReadStatusMessage(message_id="m", recipient=address).recipient == address


@pytest.mark.parametrize("field", ["recipient", "addresses"])
def test_shared_requests_reject_blank_addresses(field):
    with pytest.raises(ValidationError):
        BasicTextMessage.model_validate(
            {
                "recipient": "known",
                "text": "hi",
                field: " " if field == "recipient" else [" "],
            }
        )


@pytest.mark.parametrize(
    "platform, evidence",
    [
        (
            PlatformType.WHATSAPP,
            {"phone_number": PHONE, "bsuid": BSUID, "parent_bsuid": "CO.ENT.x"},
        ),
        (PlatformType.INSTAGRAM, {"platform_user_id": "ig:opaque"}),
    ],
)
def test_users_profiles_and_results_project_the_same_qualified_evidence(
    platform, evidence
):
    ref = InboxRef(platform=platform, inbox_id="inbox")
    user = UserBase(**evidence)
    profile = PlatformUserProfile.from_evidence(platform, user)
    result = MessageResult(
        success=True,
        platform=platform,
        inbox_id=ref.inbox_id,
        recipient=user.user_id,
        recipient_platform_id=user.platform_user_id,
        recipient_phone=user.phone_number or None,
        recipient_bsuid=user.bsuid,
        recipient_parent_bsuid=user.parent_bsuid,
    )
    assert (
        user.identity(ref).user_id
        == profile.identity(ref).user_id
        == result.identity().user_id
    )
    assert (
        user.identity(ref).addresses.values
        == profile.identity(ref).addresses.values
        == result.identity().addresses.values
    )
    assert result.identity().inbox_ref == ref
    if platform is PlatformType.INSTAGRAM:
        assert result.identity().phone_number is None


@pytest.mark.parametrize("identifier", ["CO.abc", "co.ent.123456789"])
def test_classifier_understands_both_bsuid_forms(identifier):
    bsuid, phone = classify_meta_identifier(identifier)
    assert bsuid == identifier.upper() if ".ent." in identifier else bsuid == identifier
    assert phone is None
    assert classify_meta_identifier("opaque:unknown") == (None, None)
    assert classify_meta_identifier(PHONE, platform="instagram") == (None, None)


@pytest.mark.parametrize(
    "platform,recipient,expected_phone",
    [
        ("instagram", "123456789012", None),
        ("instagram", "ig:opaque", None),
        ("whatsapp", "CO.ENT.123456789012", None),
        ("whatsapp", PHONE, PHONE),
    ],
)
async def test_api_sse_envelope_uses_selected_platform_evidence(
    platform, recipient, expected_phone
):
    event = APIMessageEvent(
        platform=platform,
        inbox_id="inbox",
        user_id=recipient,
        recipient=recipient,
        message_type="text",
        request_payload={},
        response_success=True,
    )
    hub = SSEEventHub()
    subscription = await hub.subscribe()
    async with sse_event_scope(
        platform=platform, inbox_id="inbox", phone_number="stale"
    ):
        await publish_api_sse_event(hub, event)
    envelope = await subscription.queue.get()
    assert envelope["phone_number"] == expected_phone
    assert envelope["identity"]["user_id"] == recipient
    assert envelope["identity"]["inbox_ref"]["platform"] == platform
    if platform == "instagram":
        assert envelope["bsuid"] is None


@pytest.mark.parametrize("parent", [False, True])
async def test_proven_digit_echo_is_never_attempted_but_raw_evidence_survives(parent):
    digits = "123456789012"
    user = UserBase(
        phone_number=digits,
        bsuid=BSUID if parent else f"CO.{digits}",
        parent_bsuid=f"CO.ENT.{digits}" if parent else None,
    )
    client = _Client()
    result = await _wa(client).send_text(
        "hi", DirectMessage(inbox_ref=WA, addresses=user.delivery_addresses())
    )
    assert user.phone_number == digits
    assert len(client.posted) == 1
    assert client.posted[0]["recipient"] == user.bsuid
    assert result.success


async def test_real_phone_is_normalized_before_the_transport_call():
    client = _Client()
    await _wa(client).send_text(
        "hi",
        DirectMessage(
            inbox_ref=WA, addresses=DeliveryAddresses.of("+57 300 123 4567", BSUID)
        ),
    )
    assert client.posted[0]["to"] == "+573001234567"


def wa_message(family, content):
    return {
        "id": "wamid.synthetic",
        "from": PHONE,
        "timestamp": "1793710000",
        "type": family,
        family: content,
    }


def wa_envelope(message):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "200000000000002",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": PHONE,
                                "phone_number_id": "100000000000001",
                            },
                            "contacts": [
                                {"wa_id": PHONE, "profile": {"name": "Example"}}
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "family", ["text", "selection", "image", "audio", "video", "document", "reaction"]
)
async def test_family_serialization_has_identical_keys_and_no_native_payload(family):
    if family == "text":
        native_wa = wa_message("text", {"body": "hello"})
        native_ig = msg(message={"mid": "m", "text": "hello"})
    elif family == "selection":
        native_wa = wa_message(
            "interactive",
            {"type": "button_reply", "button_reply": {"id": "choice", "title": "Pick"}},
        )
        native_wa["context"] = {"id": "original", "from": PHONE}
        native_ig = msg(postback={"mid": "m", "title": "Pick", "payload": "choice"})
    elif family == "reaction":
        native_wa = wa_message(
            "reaction", {"message_id": "wamid.original", "emoji": "❤️"}
        )
        native_ig = msg(reaction={"mid": "original", "action": "react", "emoji": "❤️"})
    else:
        mime = {
            "image": "image/png",
            "audio": "audio/ogg",
            "video": "video/mp4",
            "document": "application/pdf",
        }[family]
        native_wa = wa_message(
            family, {"id": "media.synthetic.123", "mime_type": mime, "sha256": "a" * 64}
        )
        native_ig = msg(
            message={
                "mid": "m",
                "attachments": [
                    {
                        "type": "file" if family == "document" else family,
                        "payload": {"url": CDN},
                    }
                ],
            }
        )
    if family == "audio":
        native_wa["audio"]["voice"] = False
    wa = await WhatsAppWebhookProcessor().translate(
        wa_envelope(native_wa), inbox_id="inbox"
    )
    ig = await parse(messaging(native_ig))
    wa_data, ig_data = wa.message.to_universal_dict(), ig.message.to_universal_dict()
    assert wa_data.keys() == ig_data.keys()
    assert (
        "whatsapp_data" not in wa_data
        and "text" not in ig_data
        and "selection" not in ig_data
    )
    assert wa.message.get_platform_data() and ig.message.get_platform_data()
    assert _normalized_webhook_payload(ig)["message"] == ig_data
    if family not in {"text", "selection", "reaction"}:
        assert wa_data["mime_type"] == mime
        assert ig_data["mime_type"] is None
        assert wa_data["media_family"] == ig_data["media_family"] == family
        assert ig_data["media_id"] == CDN


async def test_reply_context_serialization_is_shared_and_native_story_evidence_is_separate():
    ig = await parse(
        messaging(
            msg(message={"mid": "m", "text": "hello", "reply_to": {"mid": "original"}})
        )
    )
    wa = WhatsAppMessageContext(MessageContext(id="original", **{"from": PHONE}))
    assert (
        ig.message.get_context().to_universal_dict().keys()
        == wa.to_universal_dict().keys()
    )
    assert (
        ig.message.to_universal_dict()["context"]["original_message_id"] == "original"
    )
    assert "reply_to_message_id" not in ig.message.to_universal_dict()["context"]


@pytest.mark.parametrize(
    "code,category",
    [
        ("190", "authentication"),
        ("200", "permission"),
        ("131047", "messaging_window"),
        ("131062/7", "address_rejection"),
        ("4", "rate_limit"),
        ("10/2018278", "messaging_window"),
    ],
)
def test_meta_errors_keep_native_code_and_subcode_separate_from_category(
    code, category
):
    error = MetaGraphError(
        GraphResponse(outcome="rejected", error_code=code, status_code=400)
    )
    wa = handle_whatsapp_error(
        error, "send", PHONE, "inbox", logging.getLogger(__name__)
    )
    assert wa.error_evidence == meta_error_evidence(
        code, http_status=400, retry_safe=True
    )
    assert wa.error_evidence.category.value == category
    head, _, sub = code.partition("/")
    assert wa.error_evidence.platform_code == head
    assert wa.error_evidence.platform_subcode == (sub or None)
    if head == "131062":
        assert wa.error_code == "BSUID_RECIPIENT_NOT_SUPPORTED"


async def test_webhook_errors_retain_subcodes_and_do_not_infer_retry_safety_from_temporary():
    payload = wa_envelope(wa_message("text", {"body": "unused"}))
    value = payload["entry"][0]["changes"][0]["value"]
    del value["messages"]
    del value["contacts"]
    value["errors"] = [
        {"code": 4, "error_subcode": 9, "title": "Limited", "message": "wait"}
    ]
    webhook = await WhatsAppWebhookProcessor().translate(payload, inbox_id="inbox")
    error = webhook.errors[0]
    assert error.error_evidence.category is ErrorCategory.RATE_LIMIT
    assert error.error_evidence.platform_subcode == "9"
    assert error.is_temporary_error()
    assert not webhook.has_retryable_errors()


@pytest.mark.parametrize("status", [400, 500])
async def test_partial_send_is_visible_in_json_and_never_a_whole_call_refusal(status):
    result, _ = await instagram_send("split", fail_at=2, status=status)
    serialized = json.loads(result.model_dump_json())
    assert serialized["aggregate_outcome"] == "partially_accepted"
    assert serialized["parts"][0]["outcome"] == "accepted"
    assert serialized["parts"][1]["outcome"] == (
        "rejected" if status == 400 else "indeterminate"
    )
    assert "platform_response" not in serialized


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
def test_partial_rate_limit_retains_failed_part_delay(platform):
    accepted = MessageResult(success=True, platform=platform, message_id="m")
    failed = MessageResult(
        success=False,
        platform=platform,
        retry_after=30,
        error_code="4",
        error_evidence=meta_error_evidence("4", rate_limited=True, retry_safe=True),
    )
    result = with_message_parts(
        failed, [message_part("text", "a", accepted), message_part("text", "b", failed)]
    )
    assert aggregate_message_outcome(result).value == "partially_accepted"
    assert result.error_evidence.retry_safe is False
    assert result.parts[1].error_evidence.retry_safe is True
    assert result.parts[1].retry_after == 30
    assert json.loads(result.model_dump_json())["parts"][1]["retry_after"] == 30


async def test_single_whatsapp_send_has_serialized_accepted_part():
    result = await _wa(_Client()).send_text(
        "hi", DirectMessage(inbox_ref=WA, addresses=DeliveryAddresses.of(PHONE))
    )
    assert result.model_dump()["parts"][0]["outcome"] == "accepted"
    assert result.aggregate_outcome.value == "accepted"


@pytest.mark.parametrize(
    "platform,scope,media_ops",
    [
        ("whatsapp", "message", {"upload", "download", "info", "delete"}),
        ("instagram", "thread", {"upload", "download"}),
    ],
)
def test_discovery_and_limits_are_local_and_platform_neutral(
    platform, scope, media_ops
):
    app, resolver, _ = _app()
    client = TestClient(app)
    data = client.get(f"/api/{platform}/capabilities").json()
    assert data["read_scope"] == scope and data["typing"] is True
    assert set(data["media_operations"]) == media_ops
    assert "send_button_message" in data["operations"]
    assert "direct_message" in data["target_kinds"]
    if platform == "instagram":
        assert "send_text:private_reply" in data["operations"]
        assert ".webp" in data["media_limits"]["image"]["extensions"]
        assert ".webp" not in data["media_limits"]["image"]["upload_extensions"]
    for path in ("messages/limits", "media/limits"):
        assert client.get(f"/api/{platform}/{path}").status_code == 200
    assert resolver.calls == []


def test_meta_configuration_clean_cut_and_secret_free_diagnostics():
    config = MetaApplicationConfig(
        app_secret=SecretStr("secret"), webhook_verify_token=SecretStr("verify")
    )
    assert config.webhook_verify_token.get_secret_value() == "verify"
    assert ':"verify"' not in config.model_dump_json()
    with pytest.raises(ValidationError):
        MetaApplicationConfig(
            app_secret=SecretStr("secret"),
            whatsapp_webhook_verify_token=SecretStr("verify"),
        )


@pytest.mark.parametrize(
    "code", ["190/9", "10/2534022", "100/2534014", "131062/7", "4/8"]
)
async def test_both_send_adapters_classify_the_same_native_error_evidence(code):
    from test_interactive_header import _ig

    from wappa.domain.results import OperationOutcome

    response = GraphResponse(
        outcome=OperationOutcome.REJECTED, status_code=400, error_code=code
    )
    wa = handle_whatsapp_error(
        MetaGraphError(response), "send", PHONE, "inbox", logging.getLogger(__name__)
    )
    ig, client, _ = _ig()
    try:
        result = ig._result(response, "ig:opaque", "send")
        assert result.error_evidence == wa.error_evidence
        assert result.error_code == code  # historical IG code/subcode retained
    finally:
        await client.aclose()


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
async def test_discovery_forwards_through_pipeline_and_platform_messenger(platform):
    from test_interactive_header import _ig

    from wappa.messaging import MessengerPipeline
    from wappa.platforms import PLATFORMS, platform_messenger

    ig, client, _ = _ig()
    try:
        adapter = _wa(_Client()) if platform == "whatsapp" else ig
        pipeline = MessengerPipeline(adapter, [])
        facade = platform_messenger(pipeline)
        assert pipeline.discovery == facade.discovery == adapter.discovery
        assert facade.discovery == PLATFORMS[adapter.platform].discovery
    finally:
        await client.aclose()


async def test_invalid_whatsapp_address_is_refused_at_adapter_boundary_without_io():
    request = BasicTextMessage(recipient="ig:opaque", text="hello")
    client = _Client()
    result = await _wa(client).send_text(
        request.text,
        DirectMessage(inbox_ref=WA, addresses=DeliveryAddresses.of(request.recipient)),
    )
    assert not result.success
    assert result.aggregate_outcome.value == "rejected"
    assert client.posted == []


def test_identity_projection_excludes_proven_echo_but_keeps_native_user_evidence():
    from wappa.core.sse.context import derive_identifiers

    user = UserBase(phone_number="123456789012", bsuid="CO.123456789012")
    assert user.identity(WA).phone_number is None
    assert (
        PlatformUserProfile.from_evidence(PlatformType.WHATSAPP, user)
        .identity(WA)
        .phone_number
        is None
    )
    assert derive_identifiers(user) == (user.bsuid, None)
    assert user.phone_number == "123456789012"
