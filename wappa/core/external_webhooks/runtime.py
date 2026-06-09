"""Runtime orchestration for External Webhook Source events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from fastapi import Request

from wappa.core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from wappa.core.context import WappaContext
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.core.events.external_event_dispatcher import ExternalEventDispatcher
    from wappa.domain.interfaces.webhook_processor import IWebhookProcessor


class ExternalWebhookProcessStatus(StrEnum):
    """Internal outcome for one External Webhook Runtime dispatch attempt."""

    ACCEPTED_DISPATCH = "accepted_dispatch"
    INBOX_MISMATCH = "inbox_mismatch"
    PARSE_FAILURE = "parse_failure"
    UNRESOLVED_USER = "unresolved_user"
    DISPATCH_FAILURE = "dispatch_failure"


@dataclass(frozen=True, slots=True)
class ExternalWebhookProcessResult:
    """Observable result returned by ``ExternalWebhookRuntime.process``."""

    status: ExternalWebhookProcessStatus
    external_source: str
    inbox_id: str
    event_type: str | None = None
    user_id: str | None = None
    error: str | None = None


class WappaContextCreator(Protocol):
    """Minimal context factory interface needed by ExternalWebhookRuntime."""

    async def create_context(
        self,
        inbox_id: str,
        user_id: str | None = None,
        *,
        include_messenger: bool = False,
    ) -> WappaContext:
        """Create a Dispatch Context for an External Webhook Source event."""
        ...


def clone_request_with_body(request: Request, body: bytes) -> Request:
    """Create a Request snapshot that can be consumed by background work."""
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
    """Turns an accepted External Webhook Source request into handler dispatch."""

    def __init__(
        self,
        *,
        external_source: str,
        processor: IWebhookProcessor,
        event_handler: WappaEventHandler,
        context_factory: WappaContextCreator,
        dispatcher: ExternalEventDispatcher,
    ) -> None:
        self.external_source = external_source
        self.processor = processor
        self.event_handler = event_handler
        self.context_factory = context_factory
        self.dispatcher = dispatcher
        self.logger = get_app_logger()

    def _result(
        self,
        status: ExternalWebhookProcessStatus,
        inbox_id: str,
        *,
        event_type: str | None = None,
        user_id: str | None = None,
        error: str | None = None,
    ) -> ExternalWebhookProcessResult:
        """Build an observable result tied to this runtime and Inbox."""
        return ExternalWebhookProcessResult(
            status=status,
            external_source=self.external_source,
            inbox_id=inbox_id,
            event_type=event_type,
            user_id=user_id,
            error=error,
        )

    async def process(
        self, request: Request, inbox_id: str
    ) -> ExternalWebhookProcessResult:
        """Process one accepted external webhook in tracked background work."""
        try:
            event = await self.processor.parse_event(request, inbox_id)
        except Exception as exc:
            self.logger.error(
                "Error parsing external webhook for %s, inbox=%s: %s",
                self.external_source,
                inbox_id,
                exc,
                exc_info=True,
            )
            return self._result(
                ExternalWebhookProcessStatus.PARSE_FAILURE,
                inbox_id,
                error=str(exc),
            )

        try:
            if event.inbox_id != inbox_id:
                self.logger.error(
                    "External event inbox mismatch for %s: route=%s event=%s",
                    self.external_source,
                    inbox_id,
                    event.inbox_id,
                )
                return self._result(
                    ExternalWebhookProcessStatus.INBOX_MISMATCH,
                    inbox_id,
                    event_type=event.event_type,
                    error=f"event inbox {event.inbox_id!r} != route inbox {inbox_id!r}",
                )

            self.logger.info(
                "Parsed external event: %s/%s (inbox=%s)",
                event.source,
                event.event_type,
                inbox_id,
            )

            context = await self.context_factory.create_context(inbox_id)
            user_id = await self.processor.resolve_user_id(event, context.db)
            event.user_id = user_id
            status = ExternalWebhookProcessStatus.ACCEPTED_DISPATCH

            if user_id:
                context = await self.context_factory.create_context(
                    inbox_id=inbox_id,
                    user_id=user_id,
                    include_messenger=True,
                )
            else:
                status = ExternalWebhookProcessStatus.UNRESOLVED_USER

            request_handler = self.event_handler.with_context(
                inbox_id=inbox_id,
                user_id=user_id or "",
                messenger=context.messenger,
                cache_factory=context.cache_factory,
                db=context.db,
                db_read=context.db_read,
            )

            result = await self.dispatcher.dispatch(event, request_handler)
            if not result.get("success"):
                self.logger.error(
                    "External event dispatch failed for %s: %s",
                    self.external_source,
                    result.get("error"),
                )
                return self._result(
                    ExternalWebhookProcessStatus.DISPATCH_FAILURE,
                    inbox_id,
                    event_type=event.event_type,
                    user_id=user_id,
                    error=str(result.get("error") or "dispatch failed"),
                )

            return self._result(
                status,
                inbox_id,
                event_type=event.event_type,
                user_id=user_id,
            )

        except Exception as exc:
            self.logger.error(
                "Error processing external webhook for %s, inbox=%s: %s",
                self.external_source,
                inbox_id,
                exc,
                exc_info=True,
            )
            return self._result(
                ExternalWebhookProcessStatus.DISPATCH_FAILURE,
                inbox_id,
                error=str(exc),
            )
