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
    set_request_context,
)
from wappa.core.logging.logger import get_logger
from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.core.sse.context import (
    classify_meta_identifier,
    derive_identifiers,
    sse_event_scope,
)
from wappa.domain.factories import MessengerFactory
from wappa.persistence.cache_factory import create_cache_factory
from wappa.processors.factory import processor_factory
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.webhooks.core.webhook_interfaces import StatusWebhook


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

            # For status webhooks, attempt a best-effort phone → BSUID enrichment
            # when Meta only provides a wa_id (BSUID absent). Uses Redis scan when
            # available; silently skips for other backends or misses.
            from wappa.webhooks.core.webhook_interfaces import StatusWebhook

            if (
                isinstance(universal_webhook, StatusWebhook)
                and not universal_webhook.has_recipient_bsuid
            ):
                enriched = await self._enrich_status_user_id(
                    universal_webhook, effective_tenant_id, request
                )
                if enriched:
                    universal_webhook.user_id = enriched
                    set_request_context(tenant_id=effective_tenant_id, user_id=enriched)

            # System-level webhooks may not carry user identity; use internal fallback.
            user_id = self._resolve_handler_user_id(get_current_user_context())

            # Resolve identity signals for the SSE envelope from the webhook
            # itself so every event emitted inside this scope (incoming,
            # outgoing bot, status, error) carries coherent bsuid/phone.
            sse_user_id, sse_bsuid, sse_phone = self._derive_sse_identity(
                universal_webhook, user_id
            )
            sse_platform = (
                universal_webhook.platform.value
                if getattr(universal_webhook, "platform", None)
                else platform_type.value
            )

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

            async with sse_event_scope(
                tenant_id=effective_tenant_id,
                user_id=sse_user_id,
                bsuid=sse_bsuid,
                phone_number=sse_phone,
                platform=sse_platform,
            ):
                dispatch_result = (
                    await self.event_dispatcher.dispatch_universal_webhook(
                        universal_webhook=universal_webhook,
                        tenant_id=effective_tenant_id,
                        request_handler=request_handler,
                    )
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
            raw_messenger = await messenger_factory.create_messenger(
                platform=platform_type,
                tenant_id=tenant_id,
            )

            # Compose cross-cutting concerns (SSE lifecycle, pub/sub
            # notifications, caching, metrics, ...) uniformly via the
            # middleware pipeline. Plugins register middleware through
            # ``WappaBuilder.add_messenger_middleware`` or append to
            # ``app.state.messenger_middleware`` during their startup hook;
            # the controller stays agnostic of any specific concern.
            messenger_middleware = getattr(
                request.app.state, "messenger_middleware", ()
            )
            messenger = MessengerPipeline(
                raw=raw_messenger,
                middleware=messenger_middleware,
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

    def _derive_sse_identity(
        self, webhook: Any, fallback_user_id: str
    ) -> tuple[str, str | None, str | None]:
        """Resolve ``(user_id, bsuid, phone_number)`` for the SSE envelope.

        Pulls identity directly off the universal webhook whenever possible so
        every SSE event fired inside this request carries aligned fields.
        Falls back to ``classify_meta_identifier`` (BSUID-shape check) for
        status/error webhooks that don't carry a ``UserBase``.
        """
        from wappa.webhooks.core.webhook_interfaces import (
            ErrorWebhook,
            IncomingMessageWebhook,
            StatusWebhook,
        )

        if isinstance(webhook, IncomingMessageWebhook) and webhook.user:
            bsuid, phone = derive_identifiers(webhook.user)
            return webhook.user.user_id or fallback_user_id, bsuid, phone

        if isinstance(webhook, StatusWebhook):
            user_id = webhook.user_id or fallback_user_id
            # classify_meta_identifier splits user_id into (bsuid, phone) by
            # shape; prefer the explicit recipient_phone_id when Meta sent one.
            bsuid, shape_phone = classify_meta_identifier(user_id)
            phone = webhook.recipient_phone_id or shape_phone
            return user_id, bsuid, phone

        if isinstance(webhook, ErrorWebhook):
            return fallback_user_id, None, None

        # SystemWebhook or unknown — best effort from fallback.
        bsuid, phone = classify_meta_identifier(fallback_user_id)
        return fallback_user_id, bsuid, phone

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

    async def _enrich_status_user_id(
        self,
        status: "StatusWebhook",
        tenant_id: str,
        request: Request,
    ) -> str | None:
        """
        Best-effort phone → canonical user_id lookup for status webhooks.

        Only runs when BSUID is absent from the Meta payload and Redis is
        configured. Returns the canonical user_id from the store when found,
        or None to preserve existing behaviour.
        """
        phone = status.recipient_phone_id
        if not phone:
            return None

        cache_type = getattr(request.app.state, "wappa_cache_type", "memory")
        if cache_type != "redis":
            return None

        try:
            redis_manager = getattr(request.app.state, "redis_manager", None)
            if not redis_manager or not redis_manager.is_initialized():
                return None

            factory_class = create_cache_factory("redis")
            # user_id placeholder is irrelevant — find_by_field scans all users
            cache_factory = factory_class(tenant_id=tenant_id, user_id="__scan__")
            user_cache = cache_factory.create_user_cache()
            result = await user_cache.find_by_field("phone_number", phone)
            if result:
                return result.get("user_id") or result.get("bsuid")
        except Exception as e:
            self.logger.debug(f"Status user_id enrichment skipped: {e}")

        return None

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
