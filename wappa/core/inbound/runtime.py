"""Inbound Runtime orchestration and Dispatch Context construction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from wappa.core.events import WappaEventDispatcher
from wappa.core.logging.context import set_request_context
from wappa.core.logging.logger import get_logger
from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.core.sse.context import (
    classify_meta_identifier,
    derive_identifiers,
    sse_event_scope,
)
from wappa.domain.factories import MessengerFactory
from wappa.domain.interfaces.inbox_credential_store import IInboxCredentialStore
from wappa.persistence.cache_factory import create_cache_factory
from wappa.processors.base_processor import ProcessorError
from wappa.processors.factory import processor_factory
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces import (
    ErrorWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemWebhook,
    UniversalWebhook,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger


class InboundRuntimeError(Exception):
    """Base exception for rejected inbound runtime work."""


class UnsupportedPlatformError(InboundRuntimeError):
    """Raised when a route names a platform Wappa does not support."""


class InvalidInboxError(InboundRuntimeError):
    """Raised when the routed inbox is missing or not recognized."""


class PayloadInboxMismatchError(InboundRuntimeError):
    """Raised when platform payload identity conflicts with the routed inbox."""


class ProcessorFailureError(InboundRuntimeError):
    """Raised when platform payload translation fails."""


@dataclass(frozen=True)
class InboundRuntimeDependencies:
    """Dependencies needed to build a Dispatch Context for one inbound event."""

    http_session: httpx.AsyncClient | None
    inbox_credential_store: IInboxCredentialStore
    messenger_middleware: Sequence[Any]
    cache_type: str
    redis_manager: Any | None = None
    postgres_session_manager: Any | None = None


@dataclass(frozen=True)
class DispatchContext:
    """Per-event runtime bundle used for handler dispatch."""

    inbox_id: str
    user_id: str
    platform: PlatformType
    universal_webhook: UniversalWebhook
    request_handler: WappaEventHandler
    sse_user_id: str
    sse_bsuid: str | None
    sse_phone_number: str | None
    sse_platform: str


class InboundRuntime:
    """Turns accepted platform webhooks into context-bound handler dispatch."""

    def __init__(self, event_dispatcher: WappaEventDispatcher) -> None:
        self.event_dispatcher = event_dispatcher
        self.logger = get_logger(__name__)
        self._system_user_fallback = "__system__"
        self._status_cache_scan_user = "__scan__"

    async def accept_webhook(
        self,
        *,
        platform: PlatformType,
        inbox_id: str,
        payload: dict[str, Any],
        dependencies: InboundRuntimeDependencies,
    ) -> dict[str, str]:
        """Validate, build Dispatch Context, and schedule event dispatch."""
        dispatch_context = await self.build_dispatch_context(
            platform=platform,
            inbox_id=inbox_id,
            payload=payload,
            dependencies=dependencies,
        )
        asyncio.create_task(self.dispatch(dispatch_context))
        return {"status": "accepted"}

    async def build_dispatch_context(
        self,
        *,
        platform: PlatformType,
        inbox_id: str,
        payload: dict[str, Any],
        dependencies: InboundRuntimeDependencies,
    ) -> DispatchContext:
        if not inbox_id:
            raise InvalidInboxError("Inbox ID is required")

        if not await dependencies.inbox_credential_store.validate_inbox(inbox_id):
            raise InvalidInboxError(f"Invalid or inactive inbox: {inbox_id}")

        universal_webhook = await self._create_universal_webhook(
            platform=platform,
            inbox_id=inbox_id,
            payload=payload,
        )
        self._validate_payload_inbox(inbox_id, universal_webhook)

        if isinstance(universal_webhook, StatusWebhook):
            await self._enrich_status_user_id(universal_webhook, inbox_id, dependencies)

        user_id = self._resolve_handler_user_id(universal_webhook)
        set_request_context(inbox_id=inbox_id, user_id=user_id)

        sse_user_id, sse_bsuid, sse_phone_number = self._derive_sse_identity(
            universal_webhook, user_id
        )
        sse_platform = (
            universal_webhook.platform.value
            if getattr(universal_webhook, "platform", None)
            else platform.value
        )

        request_handler = await self._create_dispatch_handler(
            platform=platform,
            inbox_id=inbox_id,
            user_id=user_id,
            dependencies=dependencies,
        )

        self.logger.info(
            "Created %s from %s (inbox: %s, user: %s)",
            type(universal_webhook).__name__,
            platform.value,
            inbox_id,
            user_id,
        )

        return DispatchContext(
            inbox_id=inbox_id,
            user_id=user_id,
            platform=platform,
            universal_webhook=universal_webhook,
            request_handler=request_handler,
            sse_user_id=sse_user_id,
            sse_bsuid=sse_bsuid,
            sse_phone_number=sse_phone_number,
            sse_platform=sse_platform,
        )

    async def dispatch(self, dispatch_context: DispatchContext) -> None:
        """Dispatch a UniversalWebhook using its Dispatch Context."""
        set_request_context(
            inbox_id=dispatch_context.inbox_id,
            user_id=dispatch_context.user_id,
        )

        try:
            async with sse_event_scope(
                inbox_id=dispatch_context.inbox_id,
                user_id=dispatch_context.sse_user_id,
                bsuid=dispatch_context.sse_bsuid,
                phone_number=dispatch_context.sse_phone_number,
                platform=dispatch_context.sse_platform,
            ):
                dispatch_result = (
                    await self.event_dispatcher.dispatch_universal_webhook(
                        universal_webhook=dispatch_context.universal_webhook,
                        inbox_id=dispatch_context.inbox_id,
                        request_handler=dispatch_context.request_handler,
                    )
                )

            if dispatch_result.get("success", False):
                self.logger.debug(
                    "Webhook processing completed successfully for inbox: %s",
                    dispatch_context.inbox_id,
                )
            else:
                self.logger.error(
                    "Webhook dispatch failed for inbox %s: %s",
                    dispatch_context.inbox_id,
                    dispatch_result.get("error"),
                )
        except Exception as exc:
            self.logger.error(
                "Error dispatching inbound webhook for inbox %s: %s",
                dispatch_context.inbox_id,
                exc,
                exc_info=True,
            )

    async def _create_universal_webhook(
        self,
        *,
        platform: PlatformType,
        inbox_id: str,
        payload: dict[str, Any],
    ) -> UniversalWebhook:
        try:
            processor = processor_factory.get_processor(platform)
            if not hasattr(processor, "create_universal_webhook"):
                raise UnsupportedPlatformError(
                    f"Processor for {platform.value} does not support Universal Webhook Interface"
                )
            universal_webhook = await processor.create_universal_webhook(
                payload=payload,
                inbox_id=inbox_id,
            )
            return cast(UniversalWebhook, universal_webhook)
        except UnsupportedPlatformError:
            raise
        except ProcessorError as exc:
            raise ProcessorFailureError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorFailureError(
                f"Failed to transform {platform.value} webhook: {exc}"
            ) from exc

    def _validate_payload_inbox(
        self,
        routed_inbox_id: str,
        universal_webhook: UniversalWebhook,
    ) -> None:
        payload_inbox_id = getattr(universal_webhook.inbox, "inbox_id", None)
        if payload_inbox_id and payload_inbox_id != routed_inbox_id:
            raise PayloadInboxMismatchError(
                f"Payload inbox_id {payload_inbox_id!r} does not match routed inbox_id {routed_inbox_id!r}"
            )

    async def _create_dispatch_handler(
        self,
        *,
        platform: PlatformType,
        inbox_id: str,
        user_id: str,
        dependencies: InboundRuntimeDependencies,
    ) -> WappaEventHandler:
        try:
            messenger_factory = MessengerFactory(
                dependencies.http_session,
                dependencies.inbox_credential_store,
            )
            raw_messenger = await messenger_factory.create_messenger(
                platform=platform,
                inbox_id=inbox_id,
            )
            messenger: IMessenger = MessengerPipeline(
                raw=raw_messenger,
                middleware=dependencies.messenger_middleware,
            )

            cache_factory = self._create_cache_factory(
                dependencies=dependencies,
                inbox_id=inbox_id,
                user_id=user_id,
            )

            session_manager = dependencies.postgres_session_manager
            db = session_manager.get_session if session_manager else None
            db_read = session_manager.get_read_session if session_manager else None

            base_handler = self.event_dispatcher.event_handler
            if not base_handler:
                raise RuntimeError("No event handler registered with dispatcher")

            return base_handler.with_context(
                inbox_id=inbox_id,
                user_id=user_id,
                messenger=messenger,
                cache_factory=cache_factory,
                db=db,
                db_read=db_read,
            )
        except Exception as exc:
            raise RuntimeError(f"Dispatch Context creation failed: {exc}") from exc

    def _create_cache_factory(
        self,
        *,
        dependencies: InboundRuntimeDependencies,
        inbox_id: str,
        user_id: str,
    ) -> ICacheFactory:
        cache_type = dependencies.cache_type
        if cache_type == "redis":
            redis_manager = dependencies.redis_manager
            if redis_manager is None:
                raise RuntimeError(
                    "Redis cache requested but RedisPlugin not available. "
                    "Ensure Wappa(cache='redis') is used or RedisPlugin is added manually."
                )
            if not redis_manager.is_initialized():
                raise RuntimeError(
                    "Redis cache requested but RedisManager not initialized. "
                    "Check Redis server connectivity and startup logs."
                )

        factory_class = create_cache_factory(cache_type)
        return factory_class(inbox_id=inbox_id, user_id=user_id)

    def _resolve_handler_user_id(self, universal_webhook: UniversalWebhook) -> str:
        if isinstance(universal_webhook, InboundMessageWebhook):
            return universal_webhook.user.user_id
        if isinstance(universal_webhook, SystemWebhook) and universal_webhook.user:
            return universal_webhook.user.user_id
        if isinstance(universal_webhook, StatusWebhook) and universal_webhook.user_id:
            return universal_webhook.user_id
        self.logger.debug(
            "No webhook user context found; using internal system user fallback"
        )
        return self._system_user_fallback

    def _derive_sse_identity(
        self,
        webhook: UniversalWebhook,
        fallback_user_id: str,
    ) -> tuple[str, str | None, str | None]:
        if isinstance(webhook, InboundMessageWebhook) and webhook.user:
            bsuid, phone = derive_identifiers(webhook.user)
            return webhook.user.user_id or fallback_user_id, bsuid, phone

        if isinstance(webhook, StatusWebhook):
            user_id = webhook.user_id or fallback_user_id
            bsuid, shape_phone = classify_meta_identifier(user_id)
            phone = webhook.recipient_phone_id or shape_phone
            return user_id, bsuid, phone

        if isinstance(webhook, ErrorWebhook):
            return fallback_user_id, None, None

        bsuid, phone = classify_meta_identifier(fallback_user_id)
        return fallback_user_id, bsuid, phone

    async def _enrich_status_user_id(
        self,
        status: StatusWebhook,
        inbox_id: str,
        dependencies: InboundRuntimeDependencies,
    ) -> None:
        phone = status.recipient_phone_id
        if not phone or dependencies.cache_type != "redis":
            return

        try:
            redis_manager = dependencies.redis_manager
            if redis_manager is None or not redis_manager.is_initialized():
                return

            factory_class = create_cache_factory("redis")
            cache_factory = factory_class(
                inbox_id=inbox_id,
                user_id=self._status_cache_scan_user,
            )
            user_cache: Any = cache_factory.create_user_cache()
            result = await user_cache.find_by_field("phone_number", phone)
            if result:
                status.user_id = result.get("user_id") or result.get("bsuid")
        except Exception as exc:
            self.logger.debug("Status user_id enrichment skipped: %s", exc)
