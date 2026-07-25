"""Handler registry for External Webhook Source events.

An ``IWebhookProcessor`` turns one source's HTTP request into an
``ExternalEvent``. A single source usually emits many event types, and a host
application usually wants one function per event type rather than a growing
``if event.event_type == ...`` chain inside ``process_external_event``.

``ExternalEventRegistry`` is that routing table. It is deliberately transport
free: it does not own HTTP, signature checks, or Dispatch Context. Host
applications drive it from their event handler.

    registry = ExternalEventRegistry()

    @registry.on("mercadopago", "payment.approved")
    async def credit_wallet(event: ExternalEvent) -> None:
        ...

    class MyHandler(WappaEventHandler):
        async def process_external_event(self, event):
            await registry.dispatch(event)
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from wappa.core.logging.logger import get_logger
from wappa.domain.events.external_event import ExternalEvent

ExternalEventHandler = Callable[[ExternalEvent], Awaitable[None]]

WILDCARD = "*"

logger = get_logger(__name__)


@dataclass(frozen=True)
class DispatchReport:
    """Outcome of dispatching one event across its matching handlers.

    Attributes:
        matched: Handlers selected for the event.
        succeeded: Handlers that returned without raising.
        errors: ``(handler_name, exception)`` for every handler that raised.
    """

    matched: int = 0
    succeeded: int = 0
    errors: list[tuple[str, BaseException]] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)


class ExternalEventRegistry:
    """Route ``ExternalEvent`` instances to subscribed handlers.

    Subscriptions are matched by ``(source, event_type)`` in three tiers,
    dispatched most-specific first and, within a tier, in registration order:

    1. exact — ``"payment.approved"``
    2. prefix — ``"payment.*"`` matches ``payment.approved`` and ``payment.x.y``
    3. any — ``"*"`` matches every event type from that source

    A handler subscribed through more than one tier runs once per event.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[tuple[str, str], list[ExternalEventHandler]] = {}

    def register(
        self,
        source: str,
        event_type: str,
        handler: ExternalEventHandler,
    ) -> None:
        """Subscribe ``handler`` to ``event_type`` from ``source``.

        Raises:
            ValueError: If source or event_type is blank, or handler is not an
                async callable.
        """
        key = (
            _require_non_empty(source, "source"),
            _require_non_empty(event_type, "event_type"),
        )
        if not callable(handler):
            raise ValueError("handler must be callable")
        if not inspect.iscoroutinefunction(handler):
            raise ValueError(
                f"handler {_name(handler)} must be an async function — external "
                "event dispatch is awaited"
            )
        self._subscriptions.setdefault(key, []).append(handler)

    def on(
        self, source: str, event_type: str = WILDCARD
    ) -> Callable[[ExternalEventHandler], ExternalEventHandler]:
        """Decorator form of :meth:`register`, returning the handler unchanged."""

        def decorator(handler: ExternalEventHandler) -> ExternalEventHandler:
            self.register(source, event_type, handler)
            return handler

        return decorator

    def handlers_for(self, source: str, event_type: str) -> list[ExternalEventHandler]:
        """Return matching handlers, most-specific tier first, deduplicated."""
        ordered: list[ExternalEventHandler] = []
        for key in self._matching_keys(source, event_type):
            ordered.extend(self._subscriptions.get(key, ()))

        seen: set[int] = set()
        unique: list[ExternalEventHandler] = []
        for handler in ordered:
            if id(handler) not in seen:
                seen.add(id(handler))
                unique.append(handler)
        return unique

    async def dispatch(self, event: ExternalEvent) -> DispatchReport:
        """Run every matching handler for ``event``.

        Dispatch is best-effort: a raising handler is logged and the remaining
        handlers still run, so one broken subscriber cannot silence the rest.
        Inspect the returned report when a caller needs to react to failures.
        """
        handlers = self.handlers_for(event.source, event.event_type)
        if not handlers:
            logger.debug(
                "No external event handler registered for %s/%s",
                event.source,
                event.event_type,
            )
            return DispatchReport()

        succeeded = 0
        errors: list[tuple[str, BaseException]] = []
        for handler in handlers:
            try:
                await handler(event)
                succeeded += 1
            except Exception as error:  # noqa: BLE001 - best-effort fan-out
                errors.append((_name(handler), error))
                logger.error(
                    "External event handler %s failed for %s/%s: %s",
                    _name(handler),
                    event.source,
                    event.event_type,
                    error,
                    exc_info=True,
                )

        return DispatchReport(matched=len(handlers), succeeded=succeeded, errors=errors)

    def _matching_keys(self, source: str, event_type: str) -> list[tuple[str, str]]:
        keys = [(source, event_type)]
        segments = event_type.split(".")
        # Longest prefix first: "a.b.*" before "a.*".
        for cut in range(len(segments) - 1, 0, -1):
            keys.append((source, ".".join(segments[:cut]) + ".*"))
        keys.append((source, WILDCARD))
        return keys


def _require_non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _name(handler: ExternalEventHandler) -> str:
    return getattr(handler, "__qualname__", None) or repr(handler)
