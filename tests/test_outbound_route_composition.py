"""What an embedding host can drop, and what it must keep.

These tests inspect the composed route table rather than the constructor flags,
because the promise Symphonai relies on is about which URLs exist — a flag that
is stored but never consulted would pass a constructor assertion and still
expose a raw endpoint.

The load-bearing test is `test_embedded_profile_exposes_no_unauthenticated_...`:
"mutation" has to mean every route that sends, deletes, or rewrites state, not
just the ones that send a message. See ADR-0009.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from wappa.api.routes.whatsapp_combined import create_whatsapp_router

# ── capability groups, by what an unauthenticated caller could do ────────────

ORDINARY_OUTBOUND_ROUTES = {
    ("/api/whatsapp/messages/send-text", "POST"),
    ("/api/whatsapp/messages/mark-as-read", "POST"),
    ("/api/whatsapp/media/send-image", "POST"),
    ("/api/whatsapp/media/send-video", "POST"),
    ("/api/whatsapp/media/send-audio", "POST"),
    ("/api/whatsapp/media/send-document", "POST"),
    ("/api/whatsapp/media/send-sticker", "POST"),
    ("/api/whatsapp/specialized/send-contact", "POST"),
    ("/api/whatsapp/specialized/send-location", "POST"),
    ("/api/whatsapp/specialized/send-location-request", "POST"),
}

INTERACTIVE_OUTBOUND_ROUTES = {
    ("/api/whatsapp/interactive/send-buttons", "POST"),
    ("/api/whatsapp/interactive/send-list", "POST"),
    ("/api/whatsapp/interactive/send-cta", "POST"),
    ("/api/whatsapp/interactive/send-complex-buttons", "POST"),
    ("/api/whatsapp/interactive/send-menu-list", "POST"),
}

TEMPLATE_OUTBOUND_ROUTES = {
    ("/api/whatsapp/templates/send-text", "POST"),
    ("/api/whatsapp/templates/send-media", "POST"),
    ("/api/whatsapp/templates/send-location", "POST"),
}

# Destroys a media asset on the platform.
MEDIA_MANAGEMENT_ROUTES = {("/api/whatsapp/media/{media_id}", "DELETE")}

# Creates a platform media asset. Kept under the embedded profile by design.
MEDIA_UPLOAD_ROUTES = {("/api/whatsapp/media/upload", "POST")}

# Reads, overwrites, and deletes any named recipient's conversational state.
STATE_HANDLER_ROUTES = {
    ("/api/whatsapp/state-handlers/set", "POST"),
    ("/api/whatsapp/state-handlers/get/{recipient}/{handler_value}", "GET"),
    ("/api/whatsapp/state-handlers/delete/{recipient}/{handler_value}", "DELETE"),
}

MEDIA_READ_ROUTES = {
    ("/api/whatsapp/media/info/{media_id}", "GET"),
    ("/api/whatsapp/media/download/{media_id}", "GET"),
    ("/api/whatsapp/media/limits", "GET"),
}

SERVICE_READ_ROUTES = {
    ("/api/whatsapp/health", "GET"),
    ("/api/whatsapp/messages/limits", "GET"),
    ("/api/whatsapp/interactive/limits", "GET"),
    ("/api/whatsapp/specialized/validate-contact", "POST"),
    ("/api/whatsapp/specialized/validate-coordinates", "POST"),
    ("/api/whatsapp/templates/limits", "GET"),
    ("/api/whatsapp/templates/info", "GET"),
    ("/api/whatsapp/templates/info/by-id/{template_id}", "GET"),
    ("/api/whatsapp/templates/info/by-name/{template_name}", "GET"),
    ("/api/whatsapp/templates/info/namespace", "GET"),
}

# Everything that reaches the platform or rewrites stored state. The validate-*
# routes are POST only because they take a body — they perform no I/O and
# change nothing, so they are reads for this purpose.
EVERY_MUTATION = (
    ORDINARY_OUTBOUND_ROUTES
    | INTERACTIVE_OUTBOUND_ROUTES
    | TEMPLATE_OUTBOUND_ROUTES
    | MEDIA_MANAGEMENT_ROUTES
    | MEDIA_UPLOAD_ROUTES
    | STATE_HANDLER_ROUTES
)


def routes_of(**options: object) -> set[tuple[str, str]]:
    """Mount a composed router and read back every (path, method) it exposes.

    Read from the generated schema rather than ``app.routes``: FastAPI wraps
    included routers, so walking the object graph would report the wrapper
    while the schema reports the surface a client can actually call.
    """
    app = FastAPI()
    app.include_router(create_whatsapp_router(**options))  # type: ignore[arg-type]
    return {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


# ── standalone: nothing changed ─────────────────────────────────────────────


def test_standalone_default_keeps_every_route_it_always_had() -> None:
    mounted = routes_of()

    for group in (
        ORDINARY_OUTBOUND_ROUTES,
        INTERACTIVE_OUTBOUND_ROUTES,
        MEDIA_MANAGEMENT_ROUTES,
        MEDIA_UPLOAD_ROUTES,
        MEDIA_READ_ROUTES,
        STATE_HANDLER_ROUTES,
        SERVICE_READ_ROUTES,
    ):
        assert group.issubset(mounted)
    # Templates stay opt-in; that decision is unchanged.
    assert not (TEMPLATE_OUTBOUND_ROUTES & mounted)


def test_the_explicit_standalone_profile_matches_the_default() -> None:
    assert routes_of(profile="standalone") == routes_of()


# ── embedded: the security invariant ────────────────────────────────────────


def test_embedded_profile_exposes_no_unauthenticated_mutation_but_upload() -> None:
    """The whole point: ejecting sends must eject deletes and state writes too.

    Media upload is the one deliberate exception — an embedding host still
    needs Wappa's upload path, and it is closable on its own.
    """
    mounted = routes_of(profile="embedded")

    assert EVERY_MUTATION & mounted == MEDIA_UPLOAD_ROUTES


def test_embedded_profile_keeps_every_read_and_lookup() -> None:
    mounted = routes_of(profile="embedded")

    assert MEDIA_READ_ROUTES.issubset(mounted)
    assert SERVICE_READ_ROUTES.issubset(mounted)


def test_embedded_profile_can_also_close_media_upload() -> None:
    """Then nothing that reaches the platform or stored state is left."""
    mounted = routes_of(profile="embedded", include_media_upload=False)

    assert not (EVERY_MUTATION & mounted)
    assert MEDIA_READ_ROUTES.issubset(mounted)
    assert SERVICE_READ_ROUTES.issubset(mounted)


@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        pytest.param("ordinary_outbound", False, id="ordinary-outbound-omitted"),
        pytest.param("interactive_outbound", False, id="interactive-outbound-omitted"),
        pytest.param("template_outbound", False, id="template-outbound-omitted"),
        pytest.param("media_management", False, id="media-delete-omitted"),
        pytest.param("state_handlers", False, id="state-handler-api-omitted"),
        pytest.param("media_upload", True, id="media-upload-mounted"),
        pytest.param("media_reads", True, id="media-download-lookup-mounted"),
        pytest.param("service_reads", True, id="webhooks-health-template-info-mounted"),
    ],
)
def test_embedded_host_capability_matrix(capability: str, expected: bool) -> None:
    """The matrix an embedding Symphonai host composes against."""
    mounted = routes_of(profile="embedded")
    group = {
        "ordinary_outbound": ORDINARY_OUTBOUND_ROUTES,
        "interactive_outbound": INTERACTIVE_OUTBOUND_ROUTES,
        "template_outbound": TEMPLATE_OUTBOUND_ROUTES,
        "media_management": MEDIA_MANAGEMENT_ROUTES,
        "state_handlers": STATE_HANDLER_ROUTES,
        "media_upload": MEDIA_UPLOAD_ROUTES,
        "media_reads": MEDIA_READ_ROUTES,
        "service_reads": SERVICE_READ_ROUTES,
    }[capability]

    assert bool(group & mounted) is expected
    if expected:
        assert group.issubset(mounted)


# ── how the options compose ─────────────────────────────────────────────────


def test_ejecting_sends_without_a_profile_ejects_the_other_mutations() -> None:
    """The v0.26.0 spelling now closes the whole hole, not just the sends.

    A host that already passes `include_outbound_transport=False` gets the
    fixed surface without changing a line.
    """
    assert routes_of(include_outbound_transport=False) == routes_of(profile="embedded")


def test_an_explicit_capability_overrides_the_profile() -> None:
    mounted = routes_of(profile="embedded", include_state_handler_api=True)

    assert STATE_HANDLER_ROUTES.issubset(mounted)
    # and nothing else came back with it
    assert not (ORDINARY_OUTBOUND_ROUTES & mounted)
    assert not (MEDIA_MANAGEMENT_ROUTES & mounted)


def test_a_standalone_host_can_close_one_capability_on_its_own() -> None:
    """Gating is not all-or-nothing — each group stands alone."""
    mounted = routes_of(include_media_management=False)

    assert not (MEDIA_MANAGEMENT_ROUTES & mounted)
    assert ORDINARY_OUTBOUND_ROUTES.issubset(mounted)
    assert STATE_HANDLER_ROUTES.issubset(mounted)
    assert MEDIA_READ_ROUTES.issubset(mounted)


def test_omitting_outbound_transport_removes_exactly_the_intended_groups() -> None:
    full = routes_of()
    embedded = routes_of(profile="embedded")

    assert full - embedded == (
        ORDINARY_OUTBOUND_ROUTES
        | INTERACTIVE_OUTBOUND_ROUTES
        | MEDIA_MANAGEMENT_ROUTES
        | STATE_HANDLER_ROUTES
    )
    assert embedded.issubset(full)


def test_template_transport_stays_independent_of_the_profile() -> None:
    embedded_with_templates = routes_of(
        profile="embedded", include_template_transport=True
    )

    assert TEMPLATE_OUTBOUND_ROUTES.issubset(embedded_with_templates)
    assert not (ORDINARY_OUTBOUND_ROUTES & embedded_with_templates)
    assert not (STATE_HANDLER_ROUTES & embedded_with_templates)
    assert MEDIA_READ_ROUTES.issubset(embedded_with_templates)


def test_an_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError):
        routes_of(profile="embeded")  # codespell:ignore


def test_messaging_services_stay_importable_without_any_routes() -> None:
    """Route composition never gates the `wappa.messaging` capability surface."""
    routes_of(profile="embedded", include_media_upload=False)

    from wappa.messaging import (
        IMessenger,
        InboxTemplateTransport,
        OutboundRuntime,
        TextTemplateTransportRequest,
    )

    assert all(
        obj is not None
        for obj in (
            IMessenger,
            OutboundRuntime,
            InboxTemplateTransport,
            TextTemplateTransportRequest,
        )
    )
