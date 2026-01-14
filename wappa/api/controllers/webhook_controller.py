"""
Webhook controller with per-request dependency injection.

This controller handles webhook processing with proper separation of concerns:
- Routes handle HTTP validation and responses
- Controller handles business logic and dependency management
- Per-request dependency injection for proper multi-tenant support
"""

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
from wappa.domain.factories import MessengerFactory
from wappa.persistence.cache_factory import create_cache_factory
from wappa.processors.factory import processor_factory
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler


class WebhookController:
    """
    Webhook controller with per-request dependency injection.

    Handles webhook verification and processing with proper multi-tenant support.
    Creates messenger instances per request using the tenant extracted from middleware.

    Key improvements over direct route handling:
    - Proper tenant isolation (different tenant_id per request)
    - Per-request dependency creation for multi-tenant support
    - Clean separation of HTTP concerns from business logic
    - Follows SRP and clean architecture principles
    """

    def __init__(self, event_dispatcher: WappaEventDispatcher):
        """
        Initialize webhook controller with event dispatcher.

        Args:
            event_dispatcher: WappaEventDispatcher instance with user's event handler
        """
        self.event_dispatcher = event_dispatcher
        self.logger = get_logger(__name__)

        # Get supported platforms for validation
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
        """
        Handle webhook verification (challenge-response) for messaging platforms.

        Args:
            request: FastAPI request object
            platform: The messaging platform (whatsapp, telegram, etc.)
            hub_mode: Verification mode (usually "subscribe")
            hub_verify_token: Token provided by platform for verification
            hub_challenge: Challenge string to return if verification succeeds

        Returns:
            PlainTextResponse with challenge string if verification succeeds

        Raises:
            HTTPException: For validation failures or unsupported platforms
        """
        # Extract owner from middleware
        owner_id = get_current_owner_context()

        self.logger.info(
            f"Webhook verification request for platform: {platform}, owner: {owner_id}"
        )

        # Validate platform
        if not self._is_supported_platform(platform):
            self.logger.error(
                f"Unsupported platform for webhook verification: {platform}"
            )
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        # Check if this is a verification request
        if hub_mode == "subscribe" and hub_challenge:
            # Enforce verify token equals configured value
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

        # If not a verification request, return method not allowed
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
        """
        Process incoming webhook payload with per-request dependency injection.

        This method creates fresh dependencies for each request using the correct
        tenant_id extracted from middleware, enabling proper multi-tenant support.

        Args:
            request: FastAPI request object containing HTTP session and context
            platform: The messaging platform (whatsapp, telegram, etc.)
            payload: Parsed webhook JSON payload

        Returns:
            Dict with status confirmation

        Raises:
            HTTPException: For validation failures or processing errors
        """
        # Extract owner from middleware (URL owner_id)
        owner_id = get_current_owner_context()

        # ENHANCED DEBUGGING: Show context details
        context_info = get_context_info()

        self.logger.debug(
            f"Processing webhook for platform: {platform}, owner: {owner_id}"
        )
        self.logger.debug(f"🔍 Full context info: {context_info}")
        self.logger.debug(f"🌐 Request URL: {request.url.path}")
        self.logger.debug(f"📨 Request method: {request.method}")

        # Validate platform
        if not self._is_supported_platform(platform):
            self.logger.error(
                f"Unsupported platform for webhook processing: {platform}"
            )
            raise HTTPException(
                status_code=400, detail=f"Unsupported platform: {platform}"
            )

        # Validate owner
        if not owner_id:
            self.logger.error("Missing owner ID for webhook processing")
            raise HTTPException(status_code=400, detail="Owner ID is required")

        try:
            # Get platform type for processing
            platform_type = PlatformType(platform.lower())
        except ValueError as e:
            self.logger.error(f"Invalid platform type: {platform}")
            raise HTTPException(
                status_code=400, detail=f"Invalid platform: {platform}"
            ) from e

        try:
            # Process webhook asynchronously to return immediate response
            # This prevents WhatsApp timeout (5 seconds) and duplicate retries
            asyncio.create_task(
                self._process_webhook_async(
                    request=request,
                    platform_type=platform_type,
                    owner_id=owner_id,
                    payload=payload,
                )
            )

            # Return immediate response (within milliseconds)
            self.logger.debug(
                f"✅ Webhook queued for background processing: {platform}"
            )
            return {"status": "accepted"}

        except Exception as e:
            self.logger.error(f"❌ Error processing webhook: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail="Internal server error processing webhook"
            ) from e

    async def _process_webhook_async(
        self,
        request: Request,
        platform_type: PlatformType,
        owner_id: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Asynchronous webhook processing with CLONE PATTERN for thread safety.

        This is where the CRITICAL architectural improvement happens:
        1. Extract tenant_id and user_id from request (different per request)
        2. Create a CLONED handler instance for THIS REQUEST
        3. Process webhook with isolated context (no race conditions)

        Args:
            request: FastAPI request object
            platform_type: Platform type enum
            owner_id: Owner identifier extracted from middleware (URL)
            payload: Webhook payload to process
        """
        try:
            self.logger.debug(
                f"🚀 Starting async webhook processing for {platform_type.value}, owner: {owner_id}"
            )

            # First: Get appropriate processor and create Universal Webhook
            processor = processor_factory.get_processor(platform_type)

            if hasattr(processor, "create_universal_webhook"):
                # Create Universal Webhook from processor (this sets the webhook context)
                universal_webhook = await processor.create_universal_webhook(
                    payload=payload, tenant_id=owner_id
                )

                # After webhook processing, we now have the JSON tenant_id in context
                webhook_tenant_id = get_current_tenant_context()  # From webhook JSON
                effective_tenant_id = (
                    webhook_tenant_id if webhook_tenant_id else owner_id
                )  # Fallback to URL owner_id

                # Extract user_id from context (set by webhook processor)
                user_id = get_current_user_context()
                if not user_id:
                    raise RuntimeError(
                        "No user context available for request handler creation"
                    )

                self.logger.debug(
                    f"🎯 Using tenant_id: {effective_tenant_id}, user_id: {user_id} "
                    f"(webhook_tenant: {webhook_tenant_id}, owner: {owner_id})"
                )

                # CLONE PATTERN: Create isolated handler for THIS REQUEST
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

                # Dispatch to event handler via WappaEventDispatcher with CLONED handler
                dispatch_result = (
                    await self.event_dispatcher.dispatch_universal_webhook(
                        universal_webhook=universal_webhook,
                        tenant_id=effective_tenant_id,
                        request_handler=request_handler,  # Pass cloned handler!
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
            else:
                self.logger.error(
                    f"❌ Processor for {platform_type.value} does not support Universal Webhook Interface"
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
        """
        Create a context-bound handler instance for this specific request.

        This implements the CLONE PATTERN for thread safety:
        - Each request gets its own handler instance (not a singleton!)
        - Context (tenant_id, user_id) is bound to the handler instance
        - No race conditions when concurrent requests are processed

        Args:
            request: FastAPI request object
            platform_type: Platform type for messenger creation
            tenant_id: Request-specific tenant identifier
            user_id: Request-specific user identifier

        Returns:
            Context-bound WappaEventHandler instance for this request

        Raises:
            RuntimeError: If handler creation fails
        """
        try:
            # Get HTTP session from app state (shared for connection pooling - correct scope)
            http_session = getattr(request.app.state, "http_session", None)
            if not http_session:
                self.logger.warning("No HTTP session available in app state")

            # Create MessengerFactory per request (CRITICAL - not singleton!)
            messenger_factory = MessengerFactory(http_session)

            # Create messenger with request-specific tenant_id (CRITICAL!)
            messenger = await messenger_factory.create_messenger(
                platform=platform_type,
                tenant_id=tenant_id,  # This is different per request!
            )

            # Wrap messenger with PubSub if plugin is active
            if getattr(request.app.state, "pubsub_wrap_messenger", False):
                messenger = PubSubMessengerWrapper(
                    inner=messenger,
                    tenant=tenant_id,
                    user_id=user_id,
                )

            # Create cache factory per request with context injection
            cache_factory = self._create_cache_factory(request, tenant_id, user_id)

            # Get database session factories if PostgresDatabasePlugin is registered
            session_manager = getattr(
                request.app.state, "postgres_session_manager", None
            )
            db = session_manager.get_session if session_manager else None
            db_read = session_manager.get_read_session if session_manager else None

            # Get base handler (prototype) from dispatcher
            base_handler = self.event_dispatcher._event_handler
            if not base_handler:
                raise RuntimeError("No event handler registered with dispatcher")

            # CLONE PATTERN: Create context-bound handler for THIS REQUEST
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

    def _create_cache_factory(self, request: Request, tenant_id: str, user_id: str):
        """
        Create context-aware cache factory using unified plugin architecture.

        Gets cache type from app.state.wappa_cache_type (set by WappaCorePlugin) as the
        single source of truth. Validates Redis availability for redis cache type.

        Args:
            request: FastAPI request object
            tenant_id: Tenant identifier for cache isolation
            user_id: User identifier for user-specific cache contexts

        Returns:
            Cache factory instance with injected context

        Raises:
            RuntimeError: If Redis not available or cache creation fails
        """
        try:
            # Single source of truth: app.state.wappa_cache_type (set by WappaCorePlugin)
            cache_type = getattr(request.app.state, "wappa_cache_type", "memory")

            self.logger.debug(
                f"Creating {cache_type} cache factory for tenant: {tenant_id}, user: {user_id}"
            )

            # Validate Redis availability if redis cache type is requested
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

            # Create cache factory using the detected cache type
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
            # FAIL FAST - no fallback to prevent silent failures
            raise RuntimeError(f"Cache factory creation failed: {e}") from e

    def _is_supported_platform(self, platform: str) -> bool:
        """
        Check if the platform is supported.

        Args:
            platform: Platform name to validate

        Returns:
            True if platform is supported, False otherwise
        """
        return platform.lower() in self.supported_platforms

    def get_health_status(self) -> dict[str, Any]:
        """
        Get health status of the webhook controller.

        Returns:
            Dictionary with health status information
        """
        return {
            "controller": "healthy",
            "supported_platforms": list(self.supported_platforms),
            "event_dispatcher": {
                "initialized": self.event_dispatcher is not None,
                "event_handler": (
                    self.event_dispatcher._event_handler.__class__.__name__
                    if self.event_dispatcher and self.event_dispatcher._event_handler
                    else None
                ),
            },
            "dependency_injection": "per_request",  # Key improvement!
            "multi_tenant_support": True,  # Key improvement!
        }
