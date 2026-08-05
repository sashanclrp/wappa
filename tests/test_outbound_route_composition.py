"""What an embedding host can drop, and what it must keep.

These tests inspect the composed route table rather than the constructor flags,
because the promise Symphonai relies on is about which URLs exist — a flag that
is stored but never consulted would pass a constructor assertion and still
expose a raw send endpoint.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from wappa.api.routes.whatsapp_combined import create_whatsapp_router

# Every route family that sends something to a User through Wappa's own HTTP
# surface. An embedding host owns this boundary itself.
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

MEDIA_INFRASTRUCTURE_ROUTES = {
    ("/api/whatsapp/media/upload", "POST"),
    ("/api/whatsapp/media/info/{media_id}", "GET"),
    ("/api/whatsapp/media/download/{media_id}", "GET"),
    ("/api/whatsapp/media/{media_id}", "DELETE"),
    ("/api/whatsapp/media/limits", "GET"),
}

SERVICE_ROUTES = {
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
    ("/api/whatsapp/state-handlers/set", "POST"),
    ("/api/whatsapp/state-handlers/get/{recipient}/{handler_value}", "GET"),
    ("/api/whatsapp/state-handlers/delete/{recipient}/{handler_value}", "DELETE"),
}


def routes_of(**options: bool) -> set[tuple[str, str]]:
    """Mount a composed router and read back every (path, method) it exposes.

    Read from the generated schema rather than ``app.routes``: FastAPI wraps
    included routers, so walking the object graph would report the wrapper
    while the schema reports the surface a client can actually call.
    """
    app = FastAPI()
    app.include_router(create_whatsapp_router(**options))
    return {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_standalone_default_keeps_every_ordinary_outbound_route() -> None:
    mounted = routes_of()

    assert ORDINARY_OUTBOUND_ROUTES.issubset(mounted)
    assert INTERACTIVE_OUTBOUND_ROUTES.issubset(mounted)
    assert MEDIA_INFRASTRUCTURE_ROUTES.issubset(mounted)
    assert SERVICE_ROUTES.issubset(mounted)
    # Templates stay opt-in; that decision is unchanged.
    assert not (TEMPLATE_OUTBOUND_ROUTES & mounted)


@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        pytest.param("ordinary_outbound", False, id="ordinary-outbound-omitted"),
        pytest.param("template_outbound", False, id="template-outbound-omitted"),
        pytest.param("interactive_outbound", False, id="interactive-outbound-omitted"),
        pytest.param("media_infrastructure", True, id="media-upload-download-mounted"),
        pytest.param("service", True, id="webhooks-health-template-info-mounted"),
    ],
)
def test_embedded_host_capability_matrix(capability: str, expected: bool) -> None:
    """The matrix an embedding Symphonai host composes against."""
    mounted = routes_of(include_outbound_transport=False)
    families = {
        "ordinary_outbound": ORDINARY_OUTBOUND_ROUTES,
        "template_outbound": TEMPLATE_OUTBOUND_ROUTES,
        "interactive_outbound": INTERACTIVE_OUTBOUND_ROUTES,
        "media_infrastructure": MEDIA_INFRASTRUCTURE_ROUTES,
        "service": SERVICE_ROUTES,
    }[capability]

    assert bool(families & mounted) is expected
    if expected:
        assert families.issubset(mounted)


def test_omitting_outbound_transport_hides_nothing_else() -> None:
    """Dropping the mutations removes those routes and only those routes."""
    full = routes_of()
    embedded = routes_of(include_outbound_transport=False)

    assert full - embedded == ORDINARY_OUTBOUND_ROUTES | INTERACTIVE_OUTBOUND_ROUTES
    assert embedded.issubset(full)


def test_template_and_outbound_options_are_independent() -> None:
    embedded_with_templates = routes_of(
        include_outbound_transport=False, include_template_transport=True
    )

    assert TEMPLATE_OUTBOUND_ROUTES.issubset(embedded_with_templates)
    assert not (ORDINARY_OUTBOUND_ROUTES & embedded_with_templates)
    assert MEDIA_INFRASTRUCTURE_ROUTES.issubset(embedded_with_templates)


def test_messaging_services_stay_importable_without_outbound_routes() -> None:
    """Route composition never gates the `wappa.messaging` capability surface."""
    routes_of(include_outbound_transport=False)

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
