"""Liskov for IMessenger: every parameter reaches the wire on every adapter.

One neutral value set drives every ``IMessenger`` method on WhatsApp and on
Instagram through fake HTTP. Each parameter must show up in what the adapter
sent, or be listed in ``IGNORED`` with its reason and be named in the
adapter's (or the contract's) docstring, so a parameter can never be dropped
silently (ADR-0025 rule 3, ADR-0028). A new contract parameter fails here
until it has a value, a wire marker and both adapters carry it.

The second half checks result semantics: an Instagram emulation that sends
several messages returns one ``MessageResult`` listing every part under
``platform_response["wappa_parts"]``.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.contacts import ContactCard, ContactName, ContactPhone
from wappa.domain.inbox import InboxRef
from wappa.domain.interactive import (
    CardMedia,
    InteractiveHeader,
    ListRow,
    ListSection,
    MessageCard,
    ReplyButton,
)
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.instagram.messenger import PARTS_KEY, InstagramMessengerAdapter
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
    WhatsAppMessengerAdapter,
)
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

WA, IG = PlatformType.WHATSAPP, PlatformType.INSTAGRAM
WA_DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of("573001112233")
)
IG_REF = InboxRef(platform=IG, inbox_id="17890001")
IG_DM = DirectMessage(inbox_ref=IG_REF, addresses=DeliveryAddresses.of("igsid-reach"))

OPERATIONS = tuple(
    name
    for name, member in vars(IMessenger).items()
    if inspect.iscoroutinefunction(member) and not name.startswith("_")
)


def _card(n: int) -> MessageCard:
    return MessageCard(
        header=CardMedia.image(url=f"https://example.com/card{n}.png"),
        title=f"reach-card-{n}",
        subtitle=f"reach-sub-{n}",
        buttons=(ReplyButton(id=f"reach-card-btn-{n}", title="Pick"),),
    )


# One neutral value per parameter, the same on both Platforms. A parameter
# whose type differs per method is keyed ``(method, parameter)``.
VALUES: dict[str | tuple[str, str], Any] = {
    "text": "reach-text https://example.com/reach-link",
    "reply_to_message_id": "reach-reply",
    "disable_preview": True,
    "message_id": "reach-mid",
    "typing": True,
    "image_source": "https://example.com/reach-image.png",
    "caption": "reach-caption",
    "video_source": "https://example.com/reach-video.mp4",
    "transcript": "reach-transcript",
    # WhatsApp voice notes are OGG/Opus, Instagram takes M4A: one call, each
    # adapter picks its rendition.
    "audio_source": [
        "https://example.com/reach-audio.ogg",
        "https://example.com/reach-audio.m4a",
    ],
    "is_voice": True,
    "document_source": "https://example.com/reach-doc.pdf",
    "filename": "reach-file.pdf",
    "sticker_source": [
        "https://example.com/reach-sticker.webp",
        "https://example.com/reach-sticker.png",
    ],
    "buttons": [ReplyButton(id="reach-btn", title="Reach")],
    "body": "reach-body",
    ("send_button_message", "header"): InteractiveHeader.of_text("reach-header"),
    ("send_cta_message", "header"): InteractiveHeader.of_text("reach-header"),
    ("send_list_message", "header"): "reach-header",
    "footer": "reach-footer",
    "sections": [
        ListSection(
            title="reach-section",
            rows=[ListRow(id="reach-row", title="Row", description="reach-desc")],
        )
    ],
    ("send_list_message", "button_text"): "reach-open",
    ("send_cta_message", "button_text"): "reach-cta",
    "button_url": "https://example.com/reach-cta-url",
    "cards": [_card(1), _card(2)],
    "contacts": [
        ContactCard(
            name=ContactName(first_name="Reach", last_name="Person"),
            phones=[ContactPhone(phone="+573009998877")],
        )
    ],
    "latitude": 4.711,
    "longitude": -74.0721,
    "name": "reach-place",
    "address": "reach-address",
}

# What proves a value reached the wire: substrings of the serialized request
# bodies (and URLs), all of which must appear. Per-Platform where the native
# encoding differs.
MARKERS: dict[str, Any] = {
    "text": ["reach-text"],
    "target": {WA: ["573001112233"], IG: ["igsid-reach"]},
    "reply_to_message_id": ["reach-reply"],
    "disable_preview": {WA: ['"preview_url": false']},
    "message_id": {WA: ["reach-mid"]},
    "typing": {WA: ["typing_indicator"], IG: ["typing_on"]},
    "image_source": ["reach-image.png"],
    "caption": ["reach-caption"],
    "video_source": ["reach-video.mp4"],
    "audio_source": {WA: ["reach-audio.ogg"], IG: ["reach-audio.m4a"]},
    "is_voice": {WA: ['"voice": true']},
    "transcript": {},  # no Platform field (ADR-0025 contract map)
    "document_source": ["reach-doc.pdf"],
    "filename": {WA: ["reach-file.pdf"]},
    "sticker_source": {WA: ["reach-sticker.webp"], IG: ["reach-sticker.png"]},
    "buttons": ["reach-btn"],
    "body": ["reach-body"],
    "header": ["reach-header"],
    "footer": ["reach-footer"],
    # Instagram folds the section title and row description into the text.
    "sections": ["reach-row", "reach-section", "reach-desc"],
    "button_text": ["reach-"],  # refined per method below
    "button_url": ["reach-cta-url"],
    "cards": [
        "reach-card-1",
        "reach-sub-1",
        "card1.png",
        "reach-card-btn-1",
        "reach-card-2",
    ],
    "contacts": ["Reach Person", "+573009998877"],
    "latitude": ["4.711"],
    "longitude": ["-74.0721"],
    "name": ["reach-place"],
    "address": ["reach-address"],
}
METHOD_MARKERS: dict[tuple[str, str], list[str]] = {
    ("send_list_message", "button_text"): ["reach-open"],
    ("send_cta_message", "button_text"): ["reach-cta"],
}

# Parameters an adapter does not put on the wire, each with its reason. Each
# must also be named in that adapter's (or the contract's) docstring.
IGNORED: dict[tuple[PlatformType, str, str], str] = {
    (WA, "mark_as_read", "target"): "a read receipt is addressed by message ID",
    (IG, "send_text", "disable_preview"): "Instagram has no preview switch",
    (IG, "mark_as_read", "message_id"): "Instagram reads a thread; ID is echoed",
    (WA, "send_video", "transcript"): "middleware-only metadata",
    (IG, "send_video", "transcript"): "middleware-only metadata",
    (WA, "send_audio", "transcript"): "middleware-only metadata",
    (IG, "send_audio", "transcript"): "middleware-only metadata",
    (IG, "send_audio", "is_voice"): "Instagram shows every audio as a voice note",
    (IG, "send_document", "filename"): (
        "an attachable URL has no name slot; a Path uploads under it and an "
        "unattachable URL is shared as a text naming it"
    ),
    (IG, "send_list_message", "button_text"): "WhatsApp list-opener label",
}

# Evidence-mapping reads: the value is checked in the result, not the wire.
USER_VALUES = {
    WA: UserBase(phone_number="573001112233", profile_name="reach-name"),
    IG: UserBase(platform_user_id="igsid-reach", profile_name="reach-name"),
}


class _WhatsAppClient:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.posted.append(payload)
        return {
            "messages": [{"id": f"wamid.{len(self.posted)}"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


def _whatsapp() -> tuple[WhatsAppMessengerAdapter, Callable[[], str]]:
    client = _WhatsAppClient()
    messenger = WhatsAppMessengerAdapter(
        client=client,  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=WhatsAppInteractiveHandler(client, "pnid"),  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=WhatsAppSpecializedHandler(client, "pnid"),  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    return messenger, lambda: json.dumps(client.posted, ensure_ascii=False)


class _Graph:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            json={"recipient_id": "igsid-reach", "message_id": f"mid.{self.posts}"},
        )

    @property
    def posts(self) -> int:
        return sum(1 for r in self.requests if r.method == "POST")

    def wire(self) -> str:
        return "\n".join(
            f"{r.url} {r.content.decode()}" for r in self.requests
        ).replace('":', '": ')


def _instagram(graph: _Graph) -> InstagramMessengerAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(graph))
    return InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: http,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


def _parameters(name: str) -> list[inspect.Parameter]:
    return list(inspect.signature(getattr(IMessenger, name)).parameters.values())[1:]


def _call(name: str, platform: PlatformType) -> tuple[list[Any], dict[str, Any]]:
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for param in _parameters(name):
        if param.name == "target":
            value: Any = WA_DM if platform is WA else IG_DM
        elif param.name == "user":
            value = USER_VALUES[platform]
        else:
            value = VALUES.get((name, param.name), VALUES.get(param.name))
        if param.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[param.name] = value
        else:
            args.append(value)
    return args, kwargs


def _markers(name: str, param: str, platform: PlatformType) -> list[str] | None:
    if (name, param) in METHOD_MARKERS:
        return METHOD_MARKERS[(name, param)]
    marker = MARKERS[param]
    if isinstance(marker, dict):
        return marker.get(platform)
    return marker


def _documented(adapter: type, name: str, param: str) -> bool:
    method = getattr(adapter, name)
    docs = (inspect.getdoc(method) or "") + (
        inspect.getdoc(getattr(IMessenger, name)) or ""
    )
    return param in docs or f"_ = {param}" in inspect.getsource(method)


def test_every_contract_parameter_has_a_value_and_a_marker() -> None:
    missing = [
        (name, p.name)
        for name in OPERATIONS
        for p in _parameters(name)
        if p.name not in ("target", "user")
        and p.name not in VALUES
        and (name, p.name) not in VALUES
    ]
    assert missing == [], f"Give these parameters a neutral value: {missing}"
    unmarked = {
        p.name for name in OPERATIONS for p in _parameters(name) if p.name != "user"
    } - set(MARKERS)
    assert unmarked == set(), f"Give these parameters a wire marker: {unmarked}"


@pytest.mark.parametrize("name", OPERATIONS)
@pytest.mark.parametrize("platform", [WA, IG], ids=["whatsapp", "instagram"])
async def test_every_parameter_reaches_the_wire(
    name: str, platform: PlatformType
) -> None:
    graph = _Graph()
    if platform is WA:
        messenger: IMessenger
        messenger, wire = _whatsapp()
        adapter: type = WhatsAppMessengerAdapter
    else:
        messenger, wire, adapter = (
            _instagram(graph),
            graph.wire,
            InstagramMessengerAdapter,
        )
    args, kwargs = _call(name, platform)
    result = await getattr(messenger, name)(*args, **kwargs)

    haystack = wire()
    if name == "resolve_platform_user_profile":
        haystack += result.model_dump_json()
        assert "reach-name" in haystack
        return
    assert isinstance(result, MessageResult) and result.success, result

    for param in _parameters(name):
        key = (platform, name, param.name)
        markers = _markers(name, param.name, platform)
        if key in IGNORED:
            assert markers is None or not all(m in haystack for m in markers), (
                f"{key} reaches the wire; drop it from IGNORED"
            )
            assert _documented(adapter, name, param.name), (
                f"{key} is ignored but no docstring names it"
            )
            continue
        assert markers, f"{key}: no marker and not listed in IGNORED"
        absent = [m for m in markers if m not in haystack]
        assert absent == [], f"{key} did not reach the wire: {absent}"


# ── result semantics: every Instagram emulation is one result ────────────────


def _long(word: str, size: int = 1200) -> str:
    return " ".join([word] * (size // (len(word) + 1)))


EMULATIONS: dict[str, Callable[[InstagramMessengerAdapter], Any]] = {
    "split text": lambda m: m.send_text(_long("word"), IG_DM),
    "image with caption": lambda m: m.send_image(
        "https://example.com/a.png", IG_DM, caption="cap"
    ),
    "document link": lambda m: m.send_document(
        "https://example.com/a.docx", IG_DM, filename="Report.docx", caption="cap"
    ),
    "media header buttons": lambda m: m.send_button_message(
        [ReplyButton(id="b", title="B")],
        IG_DM,
        "Body",
        header=InteractiveHeader.of_image(url="https://example.com/h.png"),
    ),
    "overflowing header buttons": lambda m: m.send_button_message(
        [ReplyButton(id="b", title="B")],
        IG_DM,
        "x" * 600,
        header=InteractiveHeader.of_text("h" * 60),
    ),
    "media header cta": lambda m: m.send_cta_message(
        "Open",
        "https://example.com",
        IG_DM,
        "Body",
        header=InteractiveHeader.of_document(
            url="https://example.com/a.pdf", filename="a.pdf"
        ),
    ),
    "carousel intro": lambda m: m.send_carousel([_card(1), _card(2)], IG_DM, "Intro"),
    "split list": lambda m: m.send_list_message(
        [
            ListSection(
                title="S",
                rows=[ListRow(id="r", title="R", description="d" * 72)],
            )
        ],
        IG_DM,
        "b" * 999,
        "Open",
    ),
    "split contacts": lambda m: m.send_contact(
        [
            ContactCard(
                name=ContactName(first_name=f"Person {i} " + "n" * 40),
                phones=[ContactPhone(phone=f"+5730000000{i:02d}")],
            )
            for i in range(20)
        ],
        IG_DM,
    ),
}


@pytest.mark.parametrize("build", EMULATIONS.values(), ids=EMULATIONS.keys())
async def test_every_instagram_emulation_returns_one_result_listing_its_parts(
    build: Callable[[InstagramMessengerAdapter], Any],
) -> None:
    graph = _Graph()
    result = await build(_instagram(graph))
    assert result.success, result
    assert graph.posts > 1, "not an emulation: one message was sent"
    parts = result.platform_response[PARTS_KEY]
    assert parts["delivered"] == graph.posts
    assert parts["message_ids"] == [f"mid.{n}" for n in range(1, graph.posts + 1)]


@pytest.mark.parametrize("name", OPERATIONS)
async def test_a_multi_message_send_always_lists_its_parts(name: str) -> None:
    """The neutral value set: any Instagram call that sent several messages."""
    graph = _Graph()
    args, kwargs = _call(name, IG)
    result = await getattr(_instagram(graph), name)(*args, **kwargs)
    if name in ("mark_as_read", "resolve_platform_user_profile"):
        return  # sender actions and reads, not messages
    if graph.posts > 1:
        assert result.platform_response[PARTS_KEY]["delivered"] == graph.posts
