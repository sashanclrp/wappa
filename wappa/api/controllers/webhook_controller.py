import asyncio
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse

from wappa.core.config.settings import settings
from wappa.core.events import WappaEventDispatcher
from wappa.core.logging.context import (
    get_context_info,
    get_current_owner_context,
    get_current_tenant_context,
    get_current_user_context,
)
from wappa.core.logging.logger import get_logger
from wappa.core.pubsub import PubSubMessengerWrapper
from wappa.core.sse import SSEEventHub, SSEMessengerWrapper
from wappa.domain.factories import MessengerFactory
from wappa.persistence.cache_factory import create_cache_factory
from wappa.processors.factory import processor_factory
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler


class WebhookController:
    # Webhook controller with per-request dependency injection.

    def __init__(self, event_dispatcher: WappaEventDispatcher):
        self.event_dispatcher = event_dispatcher
        self.logger = get_logger(__name__)
        self._system_user_fallback = "__system__"
        self.supported_platforms = {platform.value.lower() for platform in PlatformType}

        self.logger.debug(
            f"WebhookController initialized with supported platforms: {self.supported_platforms}"
        )

    async def verify_webhook(
        self,
        request: Request,
        platform: str,
        hub_mode: str = None,
        hub_verify_token: str = None,
        hub_challenge: str = None,
    ):
        owner_id = get_current_owner_context()

        self.logger.info(
            f"Webhook verification request for platform: {platform}, owner: {owner_id}"
        )

        if not self._is_supported_platform(platform):
            self.logger.error(
                f"Unsupported platform for webhook verification: {platform}"
            )
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        if hub_mode == "subscribe" and hub_challenge:
            expected = settings.whatsapp_webhook_verify_token
            if not hub_verify_token:
                self.logger.error(f"❌ Missing verification token for {platform}")
                raise HTTPException(
                    status_code=403, detail="Missing verification token"
                )

            if not expected or hub_verify_token != expected:
                self.logger.error("❌ Invalid verification token received")
                raise HTTPException(
                    status_code=403, detail="Invalid verification token"
                )

            self.logger.info(
                f"✅ Webhook verification successful for {platform}, owner: {owner_id}"
            )
            return PlainTextResponse(content=hub_challenge)

        raise HTTPException(
            status_code=405,
            detail="Method not allowed for webhook verification endpoint",
        )

    async def process_webhook(
        self,
        request: Request,
        platform: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        owner_id = get_current_owner_context()

        self.logger.debug(
            f"Processing webhook for platform: {platform}, owner: {owner_id}"
        )
        self.logger.debug(f"🔍 Full context info: {get_context_info()}")
        self.logger.debug(f"🌐 Request URL: {request.url.path}")
        self.logger.debug(f"📨 Request method: {request.method}")

        if not self._is_supported_platform(platform):
            self.logger.error(
                f"Unsupported platform for webhook processing: {platform}"
            )
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        if not owner_id:
            self.logger.error("Missing owner ID for webhook processing")
            raise HTTPException(status_code=400, detail="Owner ID is required")

        try:
            platform_type = PlatformType(platform.lower())
        except ValueError as e:
            self.logger.error(f"Invalid platform type: {platform}")
            raise HTTPException(
                status_code=400, detail=f"Invalid platform: {platform}"
            ) from e

        # Process webhook asynchronously to prevent platform timeout and duplicate retries.
        asyncio.create_task(
            self._process_webhook_async(
                request=request,
                platform_type=platform_type,
                owner_id=owner_id,
                payload=payload,
            )
        )

        self.logger.debug(f"✅ Webhook queued for background processing: {platform}")
        return {"status": "accepted"}

    async def _process_webhook_async(
        self,
        request: Request,
        platform_type: PlatformType,
        owner_id: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            self.logger.debug(
                f"🚀 Starting async webhook processing for {platform_type.value}, owner: {owner_id}"
            )

            processor = processor_factory.get_processor(platform_type)

            if not hasattr(processor, "create_universal_webhook"):
                self.logger.error(
                    f"❌ Processor for {platform_type.value} does not support Universal Webhook Interface"
                )
                return

            universal_webhook = await processor.create_universal_webhook(
                payload=payload, tenant_id=owner_id
            )

            # webhook_tenant_id comes from JSON metadata; fall back to URL owner_id.
            webhook_tenant_id = get_current_tenant_context()
            effective_tenant_id = webhook_tenant_id or owner_id

            # System-level webhooks may not carry user identity; use internal fallback.
            user_id = self._resolve_handler_user_id(get_current_user_context())

            self.logger.debug(
                f"🎯 Using tenant_id: {effective_tenant_id}, user_id: {user_id} "
                f"(webhook_tenant: {webhook_tenant_id}, owner: {owner_id})"
            )

            request_handler = await self._create_request_handler(
                request=request,
                platform_type=platform_type,
                tenant_id=effective_tenant_id,
                user_id=user_id,
            )

            self.logger.info(
                f"✨ Created {type(universal_webhook).__name__} from {platform_type.value} "
                f"(tenant: {effective_tenant_id}, user: {user_id})"
            )

            dispatch_result = await self.event_dispatcher.dispatch_universal_webhook(
                universal_webhook=universal_webhook,
                tenant_id=effective_tenant_id,
                request_handler=request_handler,
            )

            if dispatch_result.get("success", False):
                self.logger.debug(
                    f"✅ Webhook processing completed successfully for tenant: {effective_tenant_id}"
                )
            else:
                self.logger.error(
                    f"❌ Webhook dispatch failed for tenant {effective_tenant_id}: {dispatch_result.get('error')}"
                )

        except Exception as e:
            self.logger.error(
                f"❌ Error in async webhook processing for owner {owner_id}: {e}",
                exc_info=True,
            )

    async def _create_request_handler(
        self,
        request: Request,
        platform_type: PlatformType,
        tenant_id: str,
        user_id: str,
    ) -> "WappaEventHandler":
        try:
            http_session = getattr(request.app.state, "http_session", None)
            if not http_session:
                self.logger.warning("No HTTP session available in app state")

            messenger_factory = MessengerFactory(http_session)
            messenger = await messenger_factory.create_messenger(
                platform=platform_type,
                tenant_id=tenant_id,
            )

            if getattr(request.app.state, "pubsub_wrap_messenger", False):
                messenger = PubSubMessengerWrapper(
                    inner=messenger,
                    tenant=tenant_id,
                    user_id=user_id,
                )

            if getattr(request.app.state, "sse_wrap_messenger", False):
                sse_event_hub = getattr(request.app.state, "sse_event_hub", None)
                if isinstance(sse_event_hub, SSEEventHub):
                    messenger = SSEMessengerWrapper(
                        inner=messenger,
                        event_hub=sse_event_hub,
                        tenant=tenant_id,
                        user_id=user_id,
                    )

            cache_factory = self._create_cache_factory(request, tenant_id, user_id)

            session_manager = getattr(
                request.app.state, "postgres_session_manager", None
            )
            db = session_manager.get_session if session_manager else None
            db_read = session_manager.get_read_session if session_manager else None

            base_handler = self.event_dispatcher.event_handler
            if not base_handler:
                raise RuntimeError("No event handler registered with dispatcher")

            request_handler = base_handler.with_context(
                tenant_id=tenant_id,
                user_id=user_id,
                messenger=messenger,
                cache_factory=cache_factory,
                db=db,
                db_read=db_read,
            )

            self.logger.debug(
                f"✅ Created request handler for tenant={tenant_id}, user={user_id}: "
                f"messenger={messenger.__class__.__name__}, platform={platform_type.value}"
            )

            return request_handler

        except Exception as e:
            self.logger.error(
                f"❌ Failed to create request handler for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Handler creation failed: {e}") from e

    def _resolve_handler_user_id(self, user_id: str | None) -> str:
        if user_id:
            return user_id
        self.logger.debug(
            "No webhook user context found; using internal system user fallback"
        )
        return self._system_user_fallback

    def _create_cache_factory(self, request: Request, tenant_id: str, user_id: str):
        try:
            cache_type = getattr(request.app.state, "wappa_cache_type", "memory")

            self.logger.debug(
                f"Creating {cache_type} cache factory for tenant: {tenant_id}, user: {user_id}"
            )

            if cache_type == "redis":
                if not hasattr(request.app.state, "redis_manager"):
                    raise RuntimeError(
                        "Redis cache requested but RedisPlugin not available. "
                        "Ensure Wappa(cache='redis') is used or RedisPlugin is added manually."
                    )

                redis_manager = request.app.state.redis_manager
                if not redis_manager.is_initialized():
                    raise RuntimeError(
                        "Redis cache requested but RedisManager not initialized. "
                        "Check Redis server connectivity and startup logs."
                    )

            factory_class = create_cache_factory(cache_type)
            cache_factory = factory_class(tenant_id=tenant_id, user_id=user_id)

            self.logger.debug(
                f"✅ Created {cache_factory.__class__.__name__} successfully"
            )
            return cache_factory

        except Exception as e:
            self.logger.error(
                f"❌ Failed to create cache factory for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Cache factory creation failed: {e}") from e

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
            "dependency_injection": "per_request",
            "multi_tenant_support": True,
        }
