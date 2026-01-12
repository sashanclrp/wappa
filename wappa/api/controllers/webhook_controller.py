"""
Webhook controller with per-request dependency injection.

This controller handles webhook processing with proper separation of concerns:
- Routes handle HTTP validation and responses
- Controller handles business logic and dependency management
- Per-request dependency injection for proper multi-tenant support
"""

import asyncio
from typing import Any

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
        Asynchronous webhook processing with per-request dependency creation.

        This is where the CRITICAL architectural improvement happens:
        1. Extract tenant_id from request (different per request)
        2. Create MessengerFactory per request
        3. Create tenant-specific messenger
        4. Inject fresh dependencies into event handler
        5. Process webhook with correct tenant context

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

                self.logger.debug(
                    f"🎯 Using tenant_id: {effective_tenant_id} (webhook: {webhook_tenant_id}, owner: {owner_id})"
                )

                # CRITICAL: Create dependencies per request with WEBHOOK tenant_id (not URL)
                await self._inject_per_request_dependencies(
                    request, platform_type, effective_tenant_id
                )

                self.logger.info(
                    f"✨ Created {type(universal_webhook).__name__} from {platform_type.value} (effective_tenant: {effective_tenant_id})"
                )

                # Dispatch to event handler via WappaEventDispatcher
                dispatch_result = (
                    await self.event_dispatcher.dispatch_universal_webhook(
                        universal_webhook=universal_webhook,
                        tenant_id=effective_tenant_id,  # Use webhook tenant_id
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

    async def _inject_per_request_dependencies(
        self, request: Request, platform_type: PlatformType, tenant_id: str
    ) -> None:
        """
        Inject fresh dependencies into event handler for this specific request.

        This is the CORE of the architectural improvement:
        - Creates MessengerFactory with request-specific HTTP session
        - Creates messenger with request-specific tenant_id
        - Injects into event handler for this request only

        Args:
            request: FastAPI request object
            platform_type: Platform type for messenger creation
            tenant_id: Request-specific tenant identifier
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

            # Extract user_id from context (set by webhook processor) with fallback
            user_id = get_current_user_context()

            if not user_id:
                raise RuntimeError(
                    "No user context available for cache factory creation"
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

            # Inject dependencies into event handler for THIS REQUEST
            event_handler = self.event_dispatcher._event_handler
            if event_handler:
                event_handler.messenger = messenger
                event_handler.cache_factory = cache_factory

                # Inject database session factory if PostgresDatabasePlugin is registered
                session_manager = getattr(
                    request.app.state, "postgres_session_manager", None
                )
                if session_manager:
                    event_handler.db = session_manager.get_session
                    event_handler.db_read = session_manager.get_read_session
                    self.logger.debug(
                        f"✅ Injected database session factory for tenant {tenant_id}"
                    )

                self.logger.debug(
                    f"✅ Injected per-request dependencies for tenant {tenant_id}: "
                    f"messenger={messenger.__class__.__name__}, platform={platform_type.value}"
                )
            else:
                self.logger.error(
                    "❌ No event handler available for dependency injection"
                )

        except Exception as e:
            self.logger.error(
                f"❌ Failed to inject per-request dependencies for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Dependency injection failed: {e}") from e

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
