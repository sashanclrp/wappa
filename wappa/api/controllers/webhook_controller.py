from typing import Any, cast

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse

from wappa.core.config.settings import settings
from wappa.core.events import WappaEventDispatcher
from wappa.core.inbound import (
    InboundRuntime,
    InboundRuntimeDependencies,
    InvalidInboxError,
    PayloadInboxMismatchError,
    ProcessorFailureError,
    UnsupportedPlatformError,
)
from wappa.core.logging.context import get_current_inbox_context
from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.inbox_credential_store import IInboxCredentialStore
from wappa.schemas.core.types import PlatformType


class WebhookController:
    """HTTP adapter for platform webhook routes."""

    def __init__(self, event_dispatcher: WappaEventDispatcher):
        self.event_dispatcher = event_dispatcher
        self.inbound_runtime = InboundRuntime(event_dispatcher)
        self.logger = get_logger(__name__)
        self.supported_platforms = {platform.value.lower() for platform in PlatformType}

        self.logger.debug(
            "WebhookController initialized with supported platforms: %s",
            self.supported_platforms,
        )

    async def verify_webhook(
        self,
        request: Request,
        platform: str,
        hub_mode: str | None = None,
        hub_verify_token: str | None = None,
        hub_challenge: str | None = None,
    ) -> PlainTextResponse:
        inbox_id = get_current_inbox_context()

        self.logger.info(
            "Webhook verification request for platform: %s, inbox: %s",
            platform,
            inbox_id,
        )

        if not self._is_supported_platform(platform):
            self.logger.error(
                "Unsupported platform for webhook verification: %s",
                platform,
            )
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        if hub_mode == "subscribe" and hub_challenge:
            expected = settings.wp_webhook_verify_token
            if not hub_verify_token:
                self.logger.error("Missing verification token for %s", platform)
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Webhook verification for platform '{platform}' requires "
                        f"hub.verify_token query parameter — set WP_WEBHOOK_VERIFY_TOKEN "
                        f"in your .env and configure the same token in the platform dashboard"
                    ),
                )

            if not expected or hub_verify_token != expected:
                self.logger.error("Invalid verification token received")
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Webhook verification token mismatch for platform '{platform}' — "
                        f"the token sent by the platform does not match WP_WEBHOOK_VERIFY_TOKEN. "
                        f"Ensure the token in your platform dashboard matches the value in .env"
                    ),
                )

            self.logger.info(
                "Webhook verification successful for %s, inbox: %s",
                platform,
                inbox_id,
            )
            return PlainTextResponse(content=hub_challenge)

        raise HTTPException(
            status_code=405,
            detail=(
                f"Webhook verification for '{platform}' requires GET with query params: "
                f"hub.mode=subscribe, hub.challenge=<challenge>, hub.verify_token=<token>. "
                f"Received request is missing hub.mode or hub.challenge."
            ),
        )

    async def process_webhook(
        self,
        request: Request,
        inbox_id: str,
        platform: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        self.logger.debug(
            "Processing webhook for platform: %s, routed inbox: %s",
            platform,
            inbox_id,
        )

        if not self._is_supported_platform(platform):
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        if not inbox_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Inbox ID is required in the webhook URL path. "
                    "Expected format: /webhook/inboxes/{inbox_id}/{platform}"
                ),
            )

        platform_type = self._parse_platform_type(platform)

        try:
            return await self.inbound_runtime.accept_webhook(
                platform=platform_type,
                inbox_id=inbox_id,
                payload=payload,
                dependencies=self._create_runtime_dependencies(request),
            )
        except UnsupportedPlatformError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InvalidInboxError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except PayloadInboxMismatchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProcessorFailureError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self.logger.error("Inbound Runtime failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Webhook processing failed for inbox '{inbox_id}' on "
                    f"platform '{platform}': {type(exc).__name__}: {exc}"
                ),
            ) from exc

    def _create_runtime_dependencies(
        self,
        request: Request,
    ) -> InboundRuntimeDependencies:
        app_state = request.app.state
        return InboundRuntimeDependencies(
            http_session=getattr(app_state, "http_session", None),
            inbox_credential_store=self._get_inbox_credential_store(request),
            messenger_middleware=getattr(app_state, "messenger_middleware", ()),
            cache_type=getattr(app_state, "wappa_cache_type", "memory"),
            background_work_tracker=app_state.background_work_tracker,
            redis_manager=getattr(app_state, "redis_manager", None),
            postgres_session_manager=getattr(
                app_state, "postgres_session_manager", None
            ),
        )

    def _get_inbox_credential_store(self, request: Request) -> IInboxCredentialStore:
        app_state = request.app.state
        store = getattr(app_state, "inbox_credential_store", None)
        if store is None:
            raise RuntimeError(
                "IInboxCredentialStore not found in app.state — ensure "
                "WappaBuilder.with_whatsapp() or a credential store plugin "
                "was configured before startup"
            )
        return cast(IInboxCredentialStore, store)

    def _parse_platform_type(self, platform: str) -> PlatformType:
        try:
            return PlatformType(platform.lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid platform: {platform}"
            ) from exc

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
