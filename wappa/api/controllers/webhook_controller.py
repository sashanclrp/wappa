"""HTTP adapter for the Meta Platform callbacks.

The controller looks the path Platform up in the app's Platform Registry
(400 when it is not installed), authenticates the exact request bytes,
validates the JSON root, delegates routing to the Platform's
``PlatformWebhooks`` adapter and admission to the Inbound Runtime, and maps
typed failures to HTTP status codes. It never parses Platform identity itself
and never sees Table Cache names, encryption keys, or token values.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse

from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.config.settings import settings
from wappa.core.dispatch.context_builder import RuntimeCapabilities
from wappa.core.events import WappaEventDispatcher
from wappa.core.inbound import (
    InboundRuntime,
    MetaCallbackAuthenticator,
    PayloadInboxMismatchError,
    PayloadRoutingError,
    ProcessorFailureError,
    UnsupportedPlatformError,
)
from wappa.core.inbound.payload_capture import capture_payload
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.errors import (
    InboxCredentialIntegrityError,
    InboxDirectoryUnavailableError,
    InboxMembershipError,
    InboxMutationConflictError,
    InboxNotFoundError,
)
from wappa.platforms import PLATFORMS, PlatformEntry
from wappa.schemas.core.types import PlatformType

_UNAUTHORIZED_DETAIL = "Unauthorized"


class WebhookController:
    """HTTP adapter for platform webhook routes."""

    def __init__(self, event_dispatcher: WappaEventDispatcher):
        self.event_dispatcher = event_dispatcher
        self.inbound_runtime = InboundRuntime(event_dispatcher)
        self.logger = get_logger(__name__)
        if settings.capture_payloads and not settings.payload_capture_enabled:
            self.logger.warning(
                "SYSTEM_CAPTURE_PAYLOADS is ignored outside SYSTEM_ENVIRONMENT=DEV"
            )

    # ── GET verification ─────────────────────────────────────────────

    async def verify_webhook(
        self,
        request: Request,
        platform: str,
        hub_mode: str | None = None,
        hub_verify_token: str | None = None,
        hub_challenge: str | None = None,
    ) -> PlainTextResponse:
        self.logger.info("Webhook verification request for platform: %s", platform)

        self._platform_entry(request, platform)

        if hub_mode == "subscribe" and hub_challenge:
            config = self._meta_config(request)
            expected = config.whatsapp_webhook_verify_token.get_secret_value()
            if not hub_verify_token or hub_verify_token != expected:
                self.logger.error("Webhook verification token mismatch")
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Webhook verification token mismatch for platform "
                        f"'{platform}' — the token sent by the platform does not "
                        "match META_WEBHOOK_VERIFY_TOKEN."
                    ),
                )
            self.logger.info("Webhook verification successful for %s", platform)
            return PlainTextResponse(content=hub_challenge)

        raise HTTPException(
            status_code=405,
            detail=(
                f"Webhook verification for '{platform}' requires GET with query "
                "params: hub.mode=subscribe, hub.challenge=<challenge>, "
                "hub.verify_token=<token>."
            ),
        )

    # ── POST intake ──────────────────────────────────────────────────

    async def process_webhook(
        self,
        request: Request,
        platform: str,
        *,
        body: bytes,
        signature: str | None,
    ) -> dict[str, str]:
        platform_type, entry = self._platform_entry(request, platform)

        # 1. Authenticate the exact bytes before anything else touches them.
        config = self._meta_config(request)
        authenticator = MetaCallbackAuthenticator(config.app_secret)
        if not authenticator.verify(body, signature):
            raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)

        # 2. Only now decode JSON and require an object root.
        payload = self._parse_object_root(body)
        if settings.payload_capture_enabled:
            await self._capture(payload, platform_type)

        # 3. Route, prove membership, build every Dispatch Context, then schedule.
        dependencies = RuntimeCapabilities.from_app(request.app)
        try:
            deliveries = await entry.webhooks.route(
                payload, dependencies.credential_resolver
            )
            return await self.inbound_runtime.accept_webhook_batch(
                deliveries=deliveries, dependencies=dependencies
            )
        except (
            PayloadRoutingError,
            InboxNotFoundError,
            InboxMembershipError,
            UnsupportedPlatformError,
            PayloadInboxMismatchError,
            ProcessorFailureError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (
            InboxDirectoryUnavailableError,
            InboxCredentialIntegrityError,
            InboxMutationConflictError,
        ) as exc:
            self.logger.error(
                "Inbox Directory unavailable during webhook intake: %s: %s",
                type(exc).__name__,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="Inbox Directory is unavailable; the callback was not accepted",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            self.logger.error("Inbound Runtime failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Webhook processing failed for platform '{platform}': "
                    f"{type(exc).__name__}"
                ),
            ) from exc

    # ── helpers ──────────────────────────────────────────────────────

    async def _capture(self, payload: dict[str, Any], platform: PlatformType) -> None:
        """Write a redacted copy for fixtures; never affects webhook handling."""
        try:
            path = await asyncio.to_thread(
                capture_payload,
                payload,
                platform=platform.value,
                log_dir=settings.log_dir,
            )
            self.logger.debug("Captured %s webhook payload: %s", platform.value, path)
        except Exception as exc:
            self.logger.warning(
                "Payload capture failed (webhook still processed): %s: %s",
                type(exc).__name__,
                exc,
            )

    @staticmethod
    def _parse_object_root(body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail="Webhook payload is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400, detail="Webhook payload root must be a JSON object"
            )
        return payload

    @staticmethod
    def _meta_config(request: Request) -> MetaApplicationConfig:
        config = getattr(request.app.state, "meta_application_config", None)
        if not isinstance(config, MetaApplicationConfig):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Meta Application Configuration is not available; the Meta "
                    "callback cannot authenticate requests"
                ),
            )
        return config

    @staticmethod
    def platforms(request: Request) -> Mapping[PlatformType, PlatformEntry]:
        """The app's Platform Registry (``PLATFORMS`` when built by hand)."""
        return getattr(request.app.state, "platforms", None) or PLATFORMS

    def _platform_entry(
        self, request: Request, platform: str
    ) -> tuple[PlatformType, PlatformEntry]:
        """Resolve an installed Platform or answer 400; never fall through."""
        try:
            platform_type = PlatformType(platform.lower())
        except ValueError:
            platform_type = None
        entry = self.platforms(request).get(platform_type) if platform_type else None
        if platform_type is None or entry is None:
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )
        return platform_type, entry

    def get_health_status(self, request: Request) -> dict[str, Any]:
        handler = self.event_dispatcher.event_handler if self.event_dispatcher else None
        return {
            "controller": "healthy",
            "supported_platforms": sorted(p.value for p in self.platforms(request)),
            "event_dispatcher": {
                "initialized": self.event_dispatcher is not None,
                "event_handler": handler.__class__.__name__ if handler else None,
            },
            "dependency_injection": "dispatch_context",
            "multi_inbox_support": True,
        }
