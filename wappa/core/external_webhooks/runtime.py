"""Admission and dispatch for External Webhook Source events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from fastapi import Request

from wappa.core.logging.logger import get_app_logger
from wappa.domain.interfaces.external_webhook_context import (
    ResolvedExternalWebhookContext,
)
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.core.context import WappaContext
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.core.events.external_event_dispatcher import ExternalEventDispatcher
    from wappa.domain.events.external_event import ExternalEvent
    from wappa.domain.inbox.identity import InboxRef
    from wappa.domain.interfaces.external_webhook_context import (
        IExternalWebhookContextResolver,
    )
    from wappa.domain.interfaces.webhook_processor import IWebhookProcessor


class ExternalWebhookProcessStatus(StrEnum):
    """Internal outcome for background external webhook dispatch."""

    ACCEPTED_DISPATCH = "accepted_dispatch"
    DISPATCH_FAILURE = "dispatch_failure"


@dataclass(frozen=True, slots=True)
class ExternalWebhookProcessResult:
    """Observable result returned after handler dispatch."""

    status: ExternalWebhookProcessStatus
    external_source: str
    webhook_id: str | None
    inbox_ref: InboxRef | None = None
    user_id: str | None = None
    event_type: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AdmittedExternalWebhook:
    """Authenticated event and bound handler accepted for background dispatch."""

    event: ExternalEvent
    request_handler: WappaEventHandler
    webhook_id: str | None
    inbox_ref: InboxRef | None
    user_id: str | None


class WappaContextCreator(Protocol):
    """Minimal context factory interface needed by ExternalWebhookRuntime."""

    async def create_context(
        self,
        inbox_id: str | None,
        user_id: str | None = None,
        *,
        include_messenger: bool = False,
        platform: PlatformType = PlatformType.WHATSAPP,
    ) -> WappaContext:
        """Create scoped capabilities or a database-only context."""
        ...


def clone_request_with_body(request: Request, body: bytes) -> Request:
    """Create a Request snapshot that can be consumed during admission."""
    scope = dict(request.scope)
    scope["headers"] = list(request.scope.get("headers", ()))
    consumed = False

    async def receive() -> dict[str, object]:
        nonlocal consumed
        if consumed:
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class ExternalWebhookRuntime:
    """Authenticate, resolve optional context, and dispatch an external event."""

    def __init__(
        self,
        *,
        external_source: str,
        processor: IWebhookProcessor,
        event_handler: WappaEventHandler,
        context_factory: WappaContextCreator,
        dispatcher: ExternalEventDispatcher,
        context_resolver: IExternalWebhookContextResolver | None = None,
    ) -> None:
        self.external_source = external_source
        self.processor = processor
        self.event_handler = event_handler
        self.context_factory = context_factory
        self.dispatcher = dispatcher
        self.context_resolver = context_resolver
        self.logger = get_app_logger()

    async def admit(
        self,
        request: Request,
        webhook_id: str | None,
    ) -> AdmittedExternalWebhook:
        """Authenticate and bind one event before the HTTP acknowledgment."""
        event = await self.processor.parse_event(request, webhook_id)
        if event.source != self.external_source:
            raise ValueError(
                "External event source does not match its WebhookPlugin: "
                f"{event.source!r} != {self.external_source!r}"
            )

        # Route identity is transport evidence owned by Wappa, not processor output.
        event.webhook_id = webhook_id

        base_context = await self.context_factory.create_context(None)
        resolution: ResolvedExternalWebhookContext | None = None
        if self.context_resolver is not None:
            resolution = await self.context_resolver.resolve(
                request,
                event,
                base_context.db,
                base_context.db_read,
            )
            if resolution is not None and not isinstance(
                resolution, ResolvedExternalWebhookContext
            ):
                raise TypeError(
                    "External webhook context resolver must return "
                    "ResolvedExternalWebhookContext or None"
                )

        if resolution is None:
            context = base_context
            inbox_ref = None
            user_id = None
        else:
            inbox_ref = resolution.inbox_ref
            user_id = resolution.user_id
            context = await self.context_factory.create_context(
                inbox_id=inbox_ref.inbox_id,
                user_id=user_id,
                include_messenger=True,
                platform=inbox_ref.platform,
            )
            if context.messenger is None:
                raise RuntimeError(
                    "Resolved external webhook Inbox has no Messenger capability"
                )
            if user_id is not None and context.cache_factory is None:
                raise RuntimeError(
                    "Resolved external webhook User has no Cache Factory capability"
                )

        request_handler = self.event_handler.with_context(
            inbox_id=inbox_ref.inbox_id if inbox_ref else None,
            inbox_ref=inbox_ref,
            user_id=user_id,
            messenger=context.messenger,
            cache_factory=context.cache_factory,
            db=context.db,
            db_read=context.db_read,
        )
        return AdmittedExternalWebhook(
            event=event,
            request_handler=request_handler,
            webhook_id=webhook_id,
            inbox_ref=inbox_ref,
            user_id=user_id,
        )

    async def dispatch(
        self,
        admitted: AdmittedExternalWebhook,
    ) -> ExternalWebhookProcessResult:
        """Dispatch an admitted event in tracked background work."""
        event = admitted.event
        try:
            result = await self.dispatcher.dispatch(event, admitted.request_handler)
            if not result.get("success"):
                error = str(result.get("error") or "dispatch failed")
                self.logger.error(
                    "External event dispatch failed for %s: %s",
                    self.external_source,
                    error,
                )
                return self._result(admitted, error=error)
        except Exception as exc:
            self.logger.error(
                "Error dispatching external webhook for %s: %s",
                self.external_source,
                exc,
                exc_info=True,
            )
            return self._result(admitted, error=str(exc))

        return self._result(admitted)

    def _result(
        self,
        admitted: AdmittedExternalWebhook,
        *,
        error: str | None = None,
    ) -> ExternalWebhookProcessResult:
        status = (
            ExternalWebhookProcessStatus.DISPATCH_FAILURE
            if error is not None
            else ExternalWebhookProcessStatus.ACCEPTED_DISPATCH
        )
        return ExternalWebhookProcessResult(
            status=status,
            external_source=self.external_source,
            webhook_id=admitted.webhook_id,
            inbox_ref=admitted.inbox_ref,
            user_id=admitted.user_id,
            event_type=admitted.event.event_type,
            error=error,
        )
