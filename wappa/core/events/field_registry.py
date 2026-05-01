"""
Webhook field handler registry.

Apps register typed handlers for arbitrary Meta WhatsApp webhook field values
(e.g. ``message_template_status_update``, ``account_update``,
``phone_number_quality_update``) that the framework does not understand
natively. A registration carries a mandatory Pydantic parser plus an async
handler — the parser converts the raw ``value`` dict from Meta into a typed
model, and the handler receives a :class:`CustomWebhook` whose ``parsed``
attribute holds that model.

The registry is consulted in two places:

1. ``WhatsAppWebhookProcessor.parse_webhook_container`` passes the registry
   into Pydantic's validation context, which lets ``WebhookChange`` accept
   registered field names alongside the built-in literals.
2. ``WhatsAppWebhookProcessor.create_universal_webhook`` builds a
   ``CustomWebhook`` for any registered field, and ``WappaEventDispatcher``
   then awaits the registered handler.

Built-in field values (``messages``, ``user_preferences``, ``user_id_update``)
are reserved — apps cannot override them through the registry.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import CustomWebhook


BUILTIN_WEBHOOK_FIELDS: frozenset[str] = frozenset(
    {"messages", "user_preferences", "user_id_update"}
)
"""Field values handled natively by the framework — reserved from registration."""


ParserFn = Callable[[dict[str, Any]], BaseModel]
HandlerFn = Callable[["CustomWebhook"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FieldHandler:
    """A single registered (field_name, parser, handler) triple."""

    field_name: str
    parser: ParserFn
    handler: HandlerFn


class FieldHandlerRegistry:
    """In-memory registry of custom webhook field handlers."""

    def __init__(self) -> None:
        self._entries: dict[str, FieldHandler] = {}

    def register(
        self,
        field_name: str,
        *,
        parser: type[BaseModel] | ParserFn,
        handler: HandlerFn,
    ) -> None:
        """
        Register a typed handler for a custom webhook field.

        Args:
            field_name: Meta webhook ``field`` value (e.g.
                ``"message_template_status_update"``).
            parser: A Pydantic ``BaseModel`` subclass *or* a callable that
                accepts the raw ``value`` dict and returns a ``BaseModel``
                instance. Mandatory — handlers always receive typed models.
            handler: Async callable invoked with the resulting
                :class:`CustomWebhook`.

        Raises:
            ValueError: If ``field_name`` is empty, collides with a built-in
                field, or is already registered.
            TypeError: If ``parser`` is not a ``BaseModel`` subclass or
                callable, or ``handler`` is not an async function.
        """
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError("field_name must be a non-empty string")
        field_name = field_name.strip()

        if field_name in BUILTIN_WEBHOOK_FIELDS:
            raise ValueError(
                f"Cannot register built-in webhook field '{field_name}' — "
                "it is handled by the framework."
            )
        if field_name in self._entries:
            raise ValueError(f"Webhook field '{field_name}' is already registered.")

        parser_fn = self._coerce_parser(field_name, parser)

        if not inspect.iscoroutinefunction(handler):
            raise TypeError(
                f"Handler for '{field_name}' must be an async function "
                f"(got {type(handler).__name__})."
            )

        self._entries[field_name] = FieldHandler(
            field_name=field_name, parser=parser_fn, handler=handler
        )

    def get(self, field_name: str) -> FieldHandler | None:
        return self._entries.get(field_name)

    def fields(self) -> frozenset[str]:
        """Snapshot of currently registered field names."""
        return frozenset(self._entries.keys())

    def __contains__(self, field_name: object) -> bool:
        return isinstance(field_name, str) and field_name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _coerce_parser(field_name: str, parser: type[BaseModel] | ParserFn) -> ParserFn:
        if isinstance(parser, type) and issubclass(parser, BaseModel):
            model_cls = parser
            return lambda raw, _cls=model_cls: _cls.model_validate(raw)
        if callable(parser):
            return parser
        raise TypeError(
            f"Parser for '{field_name}' must be a Pydantic BaseModel subclass "
            f"or a callable returning a BaseModel (got {type(parser).__name__})."
        )
