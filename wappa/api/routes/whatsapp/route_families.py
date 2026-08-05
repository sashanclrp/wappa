"""Splitting one WhatsApp HTTP surface into independently mountable capabilities.

An embedding Host Application owns its own authenticated boundary, so it needs
Wappa's unauthenticated *mutation* routes gone — but not the read, upload, and
lookup routes that happen to share the same URL prefix. Modules that mix them
mint their routers here instead of listing paths somewhere else, so the line
stays visible right where the routes are declared.

"Mutation" is not only "sends a message". A route that deletes a media asset,
or that overwrites the conversational state of an arbitrary recipient, is just
as destructive and just as unauthenticated — see ADR-0009.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, StrEnum
from typing import Any

from fastapi import APIRouter


class WhatsAppRouteProfile(StrEnum):
    """A named starting point for which capability groups get mounted.

    A profile sets defaults only; any capability passed explicitly to
    ``create_whatsapp_router`` overrides it.
    """

    STANDALONE = "standalone"
    """Wappa owns the application boundary. Everything except Template
    mutations is mounted — the surface a standalone Wappa app has always had."""

    EMBEDDED = "embedded"
    """The Host Application owns an authenticated boundary. Every route that
    sends, deletes, or rewrites state is omitted; reads, media upload, and
    lookups stay so the host keeps Wappa's infrastructure."""


@dataclass(frozen=True, slots=True)
class WhatsAppRouteCapabilities:
    """Which groups of Wappa's WhatsApp HTTP surface are mounted."""

    outbound_transport: bool
    """Ordinary sends: text, media sends, interactive, contact, location,
    mark-as-read."""

    template_transport: bool
    """Template mutation routes."""

    media_management: bool
    """``DELETE /media/{id}`` — destroys a media asset on the platform."""

    media_upload: bool
    """``POST /media/upload`` — creates a platform media asset. The one
    mutation the embedded profile keeps, because an embedding host still needs
    Wappa's upload path; close it explicitly if that is not true for you."""

    state_handler_api: bool
    """``/state-handlers/*`` — reads, overwrites, and deletes the cached
    conversational state of any recipient named in the request."""

    @classmethod
    def for_profile(cls, profile: WhatsAppRouteProfile) -> WhatsAppRouteCapabilities:
        if profile is WhatsAppRouteProfile.EMBEDDED:
            return cls(
                outbound_transport=False,
                template_transport=False,
                media_management=False,
                media_upload=True,
                state_handler_api=False,
            )
        return cls(
            outbound_transport=True,
            template_transport=False,
            media_management=True,
            media_upload=True,
            state_handler_api=True,
        )

    def override(self, **explicit: bool | None) -> WhatsAppRouteCapabilities:
        """Apply the capabilities a caller named, ignoring the ones it did not."""
        named = {field: value for field, value in explicit.items() if value is not None}
        return replace(self, **named)


class RouteFamily:
    """Mints routers that share one prefix, tag set, and response schema.

    A module holding several capability groups asks for one router per group,
    so the group a route belongs to is decided at the decorator, in the module
    that owns it — not in a path list that drifts.
    """

    def __init__(
        self,
        *,
        prefix: str,
        tags: list[str | Enum],
        responses: dict[int | str, dict[str, Any]],
    ) -> None:
        self._prefix = prefix
        self._tags = tags
        self._responses = responses

    def router(self) -> APIRouter:
        return APIRouter(
            prefix=self._prefix, tags=self._tags, responses=self._responses
        )
