"""Classification is transport shape, and only transport shape.

The failure this suite exists to prevent: an ordinary message being treated as
a Template (or the reverse) because of who sent it, which Conversation it
belongs to, or what metadata happened to ride along. Classification must be
decidable from the validated payload schema alone.
"""

from __future__ import annotations

import pytest

from wappa.api.routes.whatsapp.whatsapp_specialized import (
    ContactRequest,
    LocationRequest,
    LocationRequestRequest,
)
from wappa.messaging import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    OutboundTransportFamily,
    OutboundTransportSubkind,
    TemplateCategory,
    TemplateTransportLocationHeader,
    TemplateTransportMediaHeader,
    TemplateTransportParameter,
    TextTemplateTransportRequest,
    UnsupportedOutboundPayloadError,
    classify_outbound_payload,
)
from wappa.messaging.whatsapp.models.basic_models import (
    BasicTextMessage,
    ReadStatusMessage,
)
from wappa.messaging.whatsapp.models.interactive_models import (
    ButtonMessage,
    CTAMessage,
    InteractiveMessage,
    ListMessage,
    ListRow,
    ListSection,
    ReplyButton,
)
from wappa.messaging.whatsapp.models.media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    MediaMessage,
    MediaType,
    StickerMessage,
    VideoMessage,
)
from wappa.messaging.whatsapp.models.specialized_models import (
    ContactCard,
    ContactMessage,
    ContactName,
    ContactPhone,
    LocationMessage,
    LocationRequestMessage,
)

RECIPIENT = "573001112233"


def contact_card() -> ContactCard:
    return ContactCard(
        name=ContactName(formatted_name="Ada Lovelace"),
        phones=[ContactPhone(phone="+573001112233")],
    )


def template_request(**overrides: object) -> TextTemplateTransportRequest:
    return TextTemplateTransportRequest(
        recipient={"kind": "phone_number", "value": RECIPIENT},
        template_name="order_update",
        category=TemplateCategory.UTILITY,
        **overrides,
    )


ORDINARY_PAYLOADS = [
    pytest.param(
        BasicTextMessage(recipient=RECIPIENT, text="hi"),
        OutboundTransportFamily.TEXT,
        None,
        "text",
        id="text",
    ),
    pytest.param(
        ImageMessage(recipient=RECIPIENT, media_source="https://x/y.png"),
        OutboundTransportFamily.MEDIA,
        OutboundTransportSubkind.IMAGE,
        "image",
        id="image",
    ),
    pytest.param(
        VideoMessage(recipient=RECIPIENT, media_source="https://x/y.mp4"),
        OutboundTransportFamily.MEDIA,
        OutboundTransportSubkind.VIDEO,
        "video",
        id="video",
    ),
    pytest.param(
        AudioMessage(recipient=RECIPIENT, media_source="https://x/y.ogg"),
        OutboundTransportFamily.MEDIA,
        OutboundTransportSubkind.AUDIO,
        "audio",
        id="audio",
    ),
    pytest.param(
        DocumentMessage(recipient=RECIPIENT, media_source="https://x/y.pdf"),
        OutboundTransportFamily.MEDIA,
        OutboundTransportSubkind.DOCUMENT,
        "document",
        id="document",
    ),
    pytest.param(
        StickerMessage(recipient=RECIPIENT, media_source="https://x/y.webp"),
        OutboundTransportFamily.MEDIA,
        OutboundTransportSubkind.STICKER,
        "sticker",
        id="sticker",
    ),
    pytest.param(
        ButtonMessage(
            recipient=RECIPIENT,
            body="pick",
            buttons=[ReplyButton(id="a", title="A")],
        ),
        OutboundTransportFamily.INTERACTIVE,
        OutboundTransportSubkind.BUTTON,
        "button",
        id="button",
    ),
    pytest.param(
        ListMessage(
            recipient=RECIPIENT,
            body="pick",
            button_text="Open",
            sections=[
                ListSection(title="S", rows=[ListRow(id="r1", title="Row")]),
            ],
        ),
        OutboundTransportFamily.INTERACTIVE,
        OutboundTransportSubkind.LIST,
        "list",
        id="list",
    ),
    pytest.param(
        CTAMessage(
            recipient=RECIPIENT,
            body="see",
            button_text="Open",
            button_url="https://example.com",
        ),
        OutboundTransportFamily.INTERACTIVE,
        OutboundTransportSubkind.CTA,
        "cta",
        id="cta",
    ),
    pytest.param(
        LocationRequestMessage(recipient=RECIPIENT, body="where are you?"),
        OutboundTransportFamily.INTERACTIVE,
        OutboundTransportSubkind.LOCATION_REQUEST,
        "location_request",
        id="location-request",
    ),
    pytest.param(
        LocationMessage(recipient=RECIPIENT, latitude=4.7, longitude=-74.0),
        OutboundTransportFamily.LOCATION,
        None,
        "location",
        id="location",
    ),
    pytest.param(
        ContactMessage(recipient=RECIPIENT, contact=contact_card()),
        OutboundTransportFamily.CONTACT,
        None,
        "contact",
        id="contact",
    ),
    pytest.param(
        ReadStatusMessage(message_id="wamid.abc"),
        OutboundTransportFamily.READ_RECEIPT,
        None,
        "read_receipt",
        id="read-receipt",
    ),
]


@pytest.mark.parametrize(
    ("payload", "family", "subkind", "message_type"), ORDINARY_PAYLOADS
)
def test_every_ordinary_payload_family_classifies(
    payload: object,
    family: OutboundTransportFamily,
    subkind: OutboundTransportSubkind | None,
    message_type: str,
) -> None:
    classification = classify_outbound_payload(payload)

    assert classification.family is family
    assert classification.subkind is subkind
    assert classification.message_type == message_type
    assert not classification.is_template


@pytest.mark.parametrize("media_type", list(MediaType))
def test_media_message_classifies_by_its_declared_media_type(
    media_type: MediaType,
) -> None:
    payload = MediaMessage(
        recipient=RECIPIENT, media_type=media_type, media_source="https://x/y"
    )

    classification = classify_outbound_payload(payload)

    assert classification.family is OutboundTransportFamily.MEDIA
    assert classification.message_type == media_type.value


TEMPLATE_PAYLOADS = [
    pytest.param(
        template_request(),
        OutboundTransportSubkind.TEXT_HEADER,
        id="text-template",
    ),
    pytest.param(
        template_request(
            body_parameters=(TemplateTransportParameter(text="ORD-1"),),
        ),
        OutboundTransportSubkind.TEXT_HEADER,
        id="text-template-with-parameters",
    ),
    pytest.param(
        template_request(routing={"policy": "category_default"}),
        OutboundTransportSubkind.TEXT_HEADER,
        id="text-template-with-explicit-routing",
    ),
    pytest.param(
        TextTemplateTransportRequest(
            recipient={"kind": "phone_number", "value": RECIPIENT},
            template_name="promo",
            category=TemplateCategory.MARKETING,
            routing={"policy": "cloud_messages_fallback"},
        ),
        OutboundTransportSubkind.TEXT_HEADER,
        id="marketing-template-with-fallback-routing",
    ),
    pytest.param(
        TextTemplateTransportRequest(
            recipient={"kind": "phone_number", "value": RECIPIENT},
            template_name="otp",
            category=TemplateCategory.AUTHENTICATION,
            authentication_method="one_tap",
        ),
        OutboundTransportSubkind.TEXT_HEADER,
        id="authentication-template",
    ),
    pytest.param(
        MediaTemplateTransportRequest(
            recipient={"kind": "bsuid", "value": "CO.ABC123"},
            template_name="receipt",
            category=TemplateCategory.UTILITY,
            media_header=TemplateTransportMediaHeader(
                media_type="image", media_id="media-1"
            ),
        ),
        OutboundTransportSubkind.MEDIA_HEADER,
        id="media-template",
    ),
    pytest.param(
        LocationTemplateTransportRequest(
            recipient={"kind": "phone_number", "value": RECIPIENT},
            template_name="pickup",
            category=TemplateCategory.UTILITY,
            location_header=TemplateTransportLocationHeader(
                latitude="4.7", longitude="-74.0", name="Store", address="Main St"
            ),
        ),
        OutboundTransportSubkind.LOCATION_HEADER,
        id="location-template",
    ),
]


@pytest.mark.parametrize(("payload", "subkind"), TEMPLATE_PAYLOADS)
def test_every_valid_template_payload_classifies_as_template(
    payload: object, subkind: OutboundTransportSubkind
) -> None:
    """All Template envelope variants collapse to one family, keeping a subkind."""
    classification = classify_outbound_payload(payload)

    assert classification.family is OutboundTransportFamily.TEMPLATE
    assert classification.is_template
    assert classification.subkind is subkind
    # The header variant does not change what kind of send this was.
    assert classification.message_type == "template"


def test_an_ordinary_message_never_becomes_a_template() -> None:
    """Payload-adjacent context cannot promote an ordinary send to a Template."""
    plain = BasicTextMessage(recipient=RECIPIENT, text="hi")
    with_domain_context = BasicTextMessage(
        recipient=RECIPIENT,
        text="hi",
        user_id="agent-7",  # host-owned identity, not a transport signal
        reply_to_message_id="wamid.origin",
    )

    for payload in (plain, with_domain_context):
        assert not classify_outbound_payload(payload).is_template
        assert classify_outbound_payload(payload).family is OutboundTransportFamily.TEXT


def test_template_naming_does_not_make_an_ordinary_message_a_template() -> None:
    """Text that talks about Templates is still a text send."""
    payload = BasicTextMessage(
        recipient=RECIPIENT,
        text="your template order_update was sent",
        user_id="template",
    )

    assert classify_outbound_payload(payload).family is OutboundTransportFamily.TEXT


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"recipient": RECIPIENT, "text": "hi"}, id="raw-dict"),
        pytest.param("send this", id="string"),
        pytest.param(None, id="none"),
        pytest.param(contact_card(), id="unrelated-schema"),
        pytest.param(
            InteractiveMessage(recipient=RECIPIENT, body="ambiguous"),
            id="abstract-interactive-base",
        ),
    ],
)
def test_shapes_that_name_no_transport_are_rejected(payload: object) -> None:
    with pytest.raises(UnsupportedOutboundPayloadError):
        classify_outbound_payload(payload)


@pytest.mark.parametrize(
    ("payload", "message_type"),
    [
        pytest.param(
            ContactRequest(recipient=RECIPIENT, contact=contact_card()),
            "contact",
            id="contact-request",
        ),
        pytest.param(
            LocationRequest(recipient=RECIPIENT, latitude=4.7, longitude=-74.0),
            "location",
            id="location-request-payload",
        ),
        pytest.param(
            LocationRequestRequest(recipient=RECIPIENT, body="where?"),
            "location_request",
            id="location-request-prompt",
        ),
    ],
)
def test_route_boundary_schemas_classify_as_the_schema_they_extend(
    payload: object, message_type: str
) -> None:
    """The HTTP models only tighten validation; they are the same transports."""
    assert classify_outbound_payload(payload).message_type == message_type


@pytest.mark.parametrize(
    ("payload", "expected_label"),
    [
        pytest.param(
            ImageMessage(recipient=RECIPIENT, media_source="https://x/y.png"),
            "image",
            id="image",
        ),
        pytest.param(
            BasicTextMessage(recipient=RECIPIENT, text="hi"), "text", id="text"
        ),
        pytest.param(
            CTAMessage(
                recipient=RECIPIENT,
                body="see",
                button_text="Open",
                button_url="https://example.com",
            ),
            "cta",
            id="cta",
        ),
    ],
)
async def test_route_layer_labels_events_from_the_payload_it_received(
    payload: object, expected_label: str
) -> None:
    """The decorator no longer restates a family the payload already carries."""
    from wappa.api.utils.event_decorators import dispatch_message_event
    from wappa.core.logging.context import clear_request_context, set_request_context
    from wappa.messaging.whatsapp.models.basic_models import MessageResult

    labels: list[str] = []
    pending: list[object] = []

    class Dispatcher:
        async def dispatch(self, event: object, request: object) -> None:
            labels.append(event.message_type)  # type: ignore[attr-defined]

    class Tracker:
        is_draining = False

        def track(self, coro: object, name: str) -> None:
            pending.append(coro)

    class State:
        background_work_tracker = Tracker()
        identity_resolver = None

    class App:
        state = State()

    class Req:
        app = App()

    @dispatch_message_event(platform="whatsapp")
    async def send(**kwargs: object) -> MessageResult:
        return MessageResult(
            success=True, message_id="wamid.1", platform="whatsapp", recipient=RECIPIENT
        )

    set_request_context(inbox_id="inbox-test")
    try:
        await send(request=payload, fastapi_request=Req(), api_dispatcher=Dispatcher())
        for coro in pending:
            await coro  # type: ignore[misc]
    finally:
        clear_request_context()

    assert labels == [expected_label]


def test_classifier_is_reachable_from_the_shallow_messaging_surface() -> None:
    import wappa.messaging as messaging

    assert "classify_outbound_payload" in messaging.__all__
    assert messaging.classify_outbound_payload is classify_outbound_payload
