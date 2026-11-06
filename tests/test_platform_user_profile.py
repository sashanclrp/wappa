"""``IMessenger.resolve_platform_user_profile`` on both Platforms (ADR-0025 rule 10)."""

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox import InboxRef
from wappa.messaging import PlatformUserProfile, ReadOutcome
from wappa.messaging.instagram.messenger import InstagramMessenger
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")
IG_USER = UserBase(platform_user_id="6551596044932863")


def _whatsapp() -> WhatsAppMessenger:
    return WhatsAppMessenger(
        client=None,  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )


def _instagram(handler) -> tuple[InstagramMessenger, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    messenger = InstagramMessenger(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: client,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    return messenger, seen


async def test_whatsapp_profile_is_the_webhook_evidence_field_for_field():
    user = UserBase(
        phone_number="573001112233",
        bsuid="CO.123",
        parent_bsuid="CO.P.9",
        username="ana.co",
        country_code="CO",
        profile_name="Ana",
    )

    profile = await _whatsapp().resolve_platform_user_profile(user)

    assert profile == PlatformUserProfile(
        platform=PlatformType.WHATSAPP,
        outcome=ReadOutcome.FOUND,
        phone_number="573001112233",
        bsuid="CO.123",
        parent_bsuid="CO.P.9",
        username="ana.co",
        country_code="CO",
        profile_name="Ana",
    )
    assert profile.found and profile.picture_url is None


async def test_whatsapp_profile_of_a_username_only_user_has_no_phone():
    profile = await _whatsapp().resolve_platform_user_profile(
        UserBase(bsuid="CO.123", username="ana.co")
    )
    assert profile.phone_number is None and profile.bsuid == "CO.123"


async def test_whatsapp_rejects_another_platforms_evidence():
    with pytest.raises(ValueError, match="WhatsApp evidence"):
        await _whatsapp().resolve_platform_user_profile(IG_USER)


async def test_instagram_lookup_is_merged_over_the_evidence():
    messenger, seen = _instagram(
        lambda r: httpx.Response(
            200,
            json={
                "name": "Ana Ruiz",
                "username": "ana.ruiz",
                "profile_pic": "https://cdn.example/ana.jpg",
                "id": "6551596044932863",
            },
        )
    )

    profile = await messenger.resolve_platform_user_profile(IG_USER)

    (request,) = seen
    assert request.method == "GET"
    assert request.url.path == "/v26.0/6551596044932863"
    assert request.url.params["fields"] == "name,username,profile_pic"
    assert request.headers["Authorization"] == "Bearer tkn"
    assert profile.found and profile.platform is PlatformType.INSTAGRAM
    assert profile.platform_user_id == "6551596044932863"
    assert (profile.profile_name, profile.username, profile.picture_url) == (
        "Ana Ruiz",
        "ana.ruiz",
        "https://cdn.example/ana.jpg",
    )
    assert profile.raw is not None and profile.raw["id"] == "6551596044932863"
    assert "raw" not in profile.model_dump()


async def test_instagram_lookup_without_a_field_keeps_the_evidence_value():
    messenger, _ = _instagram(lambda r: httpx.Response(200, json={"name": ""}))
    user = UserBase(platform_user_id="6551596044932863", username="from.webhook")

    profile = await messenger.resolve_platform_user_profile(user)

    assert profile.found and profile.username == "from.webhook"
    assert profile.profile_name is None and profile.picture_url is None


def _graph_error(status: int, code: int, subcode: int | None = None):
    error: dict = {"message": "nope", "code": code}
    if subcode is not None:
        error["error_subcode"] = subcode
    return lambda r: httpx.Response(status, json={"error": error})


def _network_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.mark.parametrize(
    ("handler", "outcome"),
    [
        (_graph_error(404, 100, 33), ReadOutcome.NOT_FOUND),
        (_graph_error(403, 200), ReadOutcome.ACCESS_DENIED),
        (_graph_error(400, 100), ReadOutcome.REJECTED),
        (_network_error, ReadOutcome.UNAVAILABLE),
    ],
    ids=["404", "403", "400", "network"],
)
async def test_instagram_lookup_failure_returns_the_evidence_with_its_outcome(
    handler, outcome
):
    messenger, _ = _instagram(handler)
    user = UserBase(platform_user_id="6551596044932863", username="from.webhook")

    profile = await messenger.resolve_platform_user_profile(user)

    assert profile.outcome is outcome and not profile.found
    assert profile.platform_user_id == "6551596044932863"
    assert profile.username == "from.webhook" and profile.raw is None


async def test_instagram_rejects_evidence_without_a_scoped_id_before_io():
    messenger, seen = _instagram(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="Instagram evidence"):
        await messenger.resolve_platform_user_profile(UserBase(phone_number="5730"))
    assert seen == []


def test_profile_is_frozen_and_closed():
    profile = PlatformUserProfile(platform=PlatformType.WHATSAPP)
    with pytest.raises(ValueError):
        PlatformUserProfile(platform=PlatformType.WHATSAPP, display_name="x")  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        profile.profile_name = "x"  # type: ignore[misc]
