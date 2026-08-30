"""HTTP adapter for the WhatsApp callback.

The controller authenticates the exact request bytes, validates the JSON
root, delegates routing and admission to Wappa modules, and maps typed
failures to HTTP status codes. It never parses Platform identity itself and
never sees Table Cache names, encryption keys, or token values.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse

from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.dispatch.context_builder import RuntimeCapabilities
from wappa.core.events import WappaEventDispatcher
from wappa.core.inbound import (
    InboundRuntime,
    MetaCallbackAuthenticator,
    PayloadInboxMismatchError,
    PayloadRoutingError,
    ProcessorFailureError,
    UnsupportedPlatformError,
    route_whatsapp_payload,
)
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.errors import (
    InboxCredentialIntegrityError,
    InboxDirectoryUnavailableError,
    InboxMembershipError,
    InboxMutationConflictError,
    InboxNotFoundError,
)
from wappa.schemas.core.types import PlatformType

_UNAUTHORIZED_DETAIL = "Unauthorized"


class WebhookController:
    """HTTP adapter for platform webhook routes."""

    def __init__(self, event_dispatcher: WappaEventDispatcher):
        self.event_dispatcher = event_dispatcher
        self.inbound_runtime = InboundRuntime(event_dispatcher)
        self.logger = get_logger(__name__)
        self.supported_platforms = {platform.value.lower() for platform in PlatformType}

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

        if not self._is_supported_platform(platform):
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

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
                        "match WP_WEBHOOK_VERIFY_TOKEN."
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
        if not self._is_supported_platform(platform):
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )
        platform_type = PlatformType(platform.lower())
        if platform_type is not PlatformType.WHATSAPP:
            raise HTTPException(
                status_code=400,
                detail="Payload-derived Inbox routing is implemented only for WhatsApp",
            )

        # 1. Authenticate the exact bytes before anything else touches them.
        config = self._meta_config(request)
        authenticator = MetaCallbackAuthenticator(config.app_secret)
        if not authenticator.verify(body, signature):
            raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)

        # 2. Only now decode JSON and require an object root.
        payload = self._parse_object_root(body)

        # 3. Route, prove membership, build every Dispatch Context, then schedule.
        dependencies = RuntimeCapabilities.from_app(request.app)
        try:
            deliveries = await route_whatsapp_payload(
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
                    "Meta Application Configuration is not available; the WhatsApp "
                    "callback cannot authenticate requests"
                ),
            )
        return config

    def _is_supported_platform(self, platform: str) -> bool:
        return platform.lower() in self.supported_platforms

    def get_health_status(self) -> dict[str, Any]:
        handler = self.event_dispatcher.event_handler if self.event_dispatcher else None
        return {
            "controller": "healthy",
            "supported_platforms": list(self.supported_platforms),
            "event_dispatcher": {
                "initialized": self.event_dispatcher is not None,
                "event_handler": handler.__class__.__name__ if handler else None,
            },
            "dependency_injection": "dispatch_context",
            "multi_inbox_support": True,
        }
