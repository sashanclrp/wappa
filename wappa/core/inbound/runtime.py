"""Inbound Runtime orchestration and Dispatch Context construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wappa.core.dispatch.context_builder import (
    DispatchContextBuilder,
    RuntimeCapabilities,
)
from wappa.core.events import WappaEventDispatcher
from wappa.core.logging.context import (
    bind_inbox_context,
    bind_user_context,
    reset_inbox_context,
    reset_user_context,
    set_request_context,
)
from wappa.core.logging.logger import get_logger
from wappa.core.sse.context import (
    classify_meta_identifier,
    derive_identifiers,
    sse_event_scope,
)
from wappa.domain.inbox.errors import InboxDirectoryError
from wappa.domain.inbox.identity import InboxRef
from wappa.persistence.cache_factory import create_cache_factory
from wappa.processors.base_processor import ProcessorError
from wappa.processors.factory import processor_factory
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces import (
    CallWebhook,
    ErrorWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemWebhook,
    UniversalWebhook,
)

from .webhook_routing import RoutedWebhookDelivery

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler

# Kept as the public name for the capability bundle the runtime consumes.
InboundRuntimeDependencies = RuntimeCapabilities


class InboundRuntimeError(Exception):
    """Base exception for rejected inbound runtime work."""


class UnsupportedPlatformError(InboundRuntimeError):
    """Raised when a route names a platform Wappa does not support."""


class PayloadInboxMismatchError(InboundRuntimeError):
    """Raised when platform payload identity conflicts with the routed inbox."""


class ProcessorFailureError(InboundRuntimeError):
    """Raised when platform payload translation fails."""


class DispatchContextError(InboundRuntimeError):
    """Raised when a Dispatch Context cannot be built for a non-directory reason."""


@dataclass(frozen=True)
class DispatchContext:
    """Per-event runtime bundle used for handler dispatch."""

    inbox_ref: InboxRef
    user_id: str
    platform: PlatformType
    universal_webhook: UniversalWebhook
    request_handler: WappaEventHandler
    sse_user_id: str
    sse_bsuid: str | None
    sse_phone_number: str | None
    sse_platform: str
    background_work_tracker: Any = None

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id


class InboundRuntime:
    """Turns accepted platform webhooks into context-bound handler dispatch."""

    def __init__(self, event_dispatcher: WappaEventDispatcher) -> None:
        self.event_dispatcher = event_dispatcher
        self.logger = get_logger(__name__)
        self._system_user_fallback = "__system__"
        self._status_cache_scan_user = "__scan__"

    async def accept_webhook_batch(
        self,
        *,
        deliveries: Sequence[RoutedWebhookDelivery],
        dependencies: RuntimeCapabilities,
    ) -> dict[str, str]:
        """Build every Dispatch Context, then schedule the whole batch.

        A failure while building item N schedules none of items 1..N-1.
        """
        builder = DispatchContextBuilder(dependencies)
        dispatch_contexts = [
            await self.build_dispatch_context(delivery, builder=builder)
            for delivery in deliveries
        ]
        for dispatch_context in dispatch_contexts:
            dependencies.background_work_tracker.track(
                self.dispatch(dispatch_context),
                name=f"inbound:{dispatch_context.inbox_id}:{dispatch_context.user_id}",
            )
        return {"status": "accepted"}

    async def build_dispatch_context(
        self,
        delivery: RoutedWebhookDelivery,
        *,
        builder: DispatchContextBuilder | None = None,
        dependencies: RuntimeCapabilities | None = None,
    ) -> DispatchContext:
        if builder is None:
            if dependencies is None:
                raise ValueError(
                    "build_dispatch_context needs a builder or dependencies"
                )
            builder = DispatchContextBuilder(dependencies)

        inbox_ref = delivery.inbox_ref
        platform = inbox_ref.platform
        universal_webhook = await self._create_universal_webhook(
            platform=platform, inbox_id=inbox_ref.inbox_id, payload=delivery.payload
        )
        self._validate_payload_inbox(inbox_ref.inbox_id, universal_webhook)

        if isinstance(universal_webhook, StatusWebhook):
            await self._enrich_status_user_id(
                universal_webhook, inbox_ref, builder.capabilities
            )

        user_id = self._resolve_handler_user_id(universal_webhook)

        # Bind identity only for the build of this delivery; build-phase logs
        # of a later delivery must not be attributed to this one.
        inbox_token = bind_inbox_context(inbox_ref.inbox_id)
        user_token = bind_user_context(user_id)
        try:
            request_handler = await self._create_dispatch_handler(
                builder=builder, delivery=delivery, user_id=user_id
            )
            self.logger.info(
                "Created %s from %s (inbox: %s, user: %s)",
                type(universal_webhook).__name__,
                platform.value,
                inbox_ref.inbox_id,
                user_id,
            )
        finally:
            reset_user_context(user_token)
            reset_inbox_context(inbox_token)

        sse_user_id, sse_bsuid, sse_phone_number = self._derive_sse_identity(
            universal_webhook, user_id
        )
        sse_platform = (
            universal_webhook.platform.value
            if getattr(universal_webhook, "platform", None)
            else platform.value
        )

        return DispatchContext(
            inbox_ref=inbox_ref,
            user_id=user_id,
            platform=platform,
            universal_webhook=universal_webhook,
            request_handler=request_handler,
            sse_user_id=sse_user_id,
            sse_bsuid=sse_bsuid,
            sse_phone_number=sse_phone_number,
            sse_platform=sse_platform,
            background_work_tracker=builder.capabilities.background_work_tracker,
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
                tracker=dispatch_context.background_work_tracker,
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
        except InboxDirectoryError as exc:
            self.logger.error(
                "Inbox Directory failure while dispatching for inbox %s: %s: %s",
                dispatch_context.inbox_id,
                type(exc).__name__,
                exc,
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
            return await processor.create_universal_webhook(
                payload=payload, inbox_id=inbox_id
            )
        except UnsupportedPlatformError:
            raise
        except ProcessorError as exc:
            raise ProcessorFailureError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorFailureError(
                f"Failed to transform {platform.value} webhook: {exc}"
            ) from exc

    def _validate_payload_inbox(
        self, routed_inbox_id: str, universal_webhook: UniversalWebhook
    ) -> None:
        payload_inbox_id = getattr(universal_webhook.inbox, "inbox_id", None)
        if payload_inbox_id and payload_inbox_id != routed_inbox_id:
            raise PayloadInboxMismatchError(
                f"Payload inbox_id {payload_inbox_id!r} does not match routed "
                f"inbox_id {routed_inbox_id!r}"
            )

    async def _create_dispatch_handler(
        self,
        *,
        builder: DispatchContextBuilder,
        delivery: RoutedWebhookDelivery,
        user_id: str,
    ) -> WappaEventHandler:
        base_handler = self.event_dispatcher.event_handler
        if not base_handler:
            raise DispatchContextError(
                "No WappaEventHandler registered with the event dispatcher — "
                "call app.set_event_handler() or WappaBuilder.with_event_handler() "
                "before processing webhooks"
            )
        try:
            messenger = await builder.messenger(
                delivery.inbox_ref, credentials=delivery.credentials
            )
            cache_factory = builder.cache_factory(delivery.inbox_ref, user_id)
        except InboxDirectoryError:
            raise
        except Exception as exc:
            raise DispatchContextError(
                f"Dispatch Context creation failed for inbox '{delivery.inbox_id}', "
                f"user '{user_id}', platform '{delivery.inbox_ref.platform.value}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return builder.bind_handler(
            base_handler,
            inbox_ref=delivery.inbox_ref,
            user_id=user_id,
            messenger=messenger,
            cache_factory=cache_factory,
        )

    def _resolve_handler_user_id(self, universal_webhook: UniversalWebhook) -> str:
        if isinstance(universal_webhook, InboundMessageWebhook):
            return universal_webhook.user.user_id
        if isinstance(universal_webhook, CallWebhook) and universal_webhook.user_id:
            return universal_webhook.user_id
        if isinstance(universal_webhook, SystemWebhook) and universal_webhook.user:
            return universal_webhook.user.user_id
        if isinstance(universal_webhook, StatusWebhook) and universal_webhook.user_id:
            return universal_webhook.user_id
        self.logger.debug(
            "No webhook user context found; using internal system user fallback"
        )
        return self._system_user_fallback

    def _derive_sse_identity(
        self, webhook: UniversalWebhook, fallback_user_id: str
    ) -> tuple[str, str | None, str | None]:
        if isinstance(webhook, InboundMessageWebhook) and webhook.user:
            bsuid, phone = derive_identifiers(webhook.user)
            return webhook.user.user_id or fallback_user_id, bsuid, phone

        if isinstance(webhook, CallWebhook):
            user_id = webhook.user_id or fallback_user_id
            return user_id, webhook.bsuid, webhook.phone_number

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
        inbox_ref: InboxRef,
        capabilities: RuntimeCapabilities,
    ) -> None:
        phone = status.recipient_phone_id
        if not phone or capabilities.cache_type != "redis":
            return

        try:
            redis_manager = capabilities.redis_manager
            if redis_manager is None or not redis_manager.is_initialized():
                return

            factory_class = create_cache_factory("redis")
            cache_factory = factory_class(
                inbox_id=inbox_ref.cache_namespace,
                user_id=self._status_cache_scan_user,
            )
            user_cache: Any = cache_factory.create_user_cache()
            result = await user_cache.find_by_field("phone_number", phone)
            if result:
                status.user_id = result.get("user_id") or result.get("bsuid")
        except Exception as exc:
            self.logger.debug("Status user_id enrichment skipped: %s", exc)
