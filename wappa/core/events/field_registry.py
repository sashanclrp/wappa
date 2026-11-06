"""
Webhook field handler registry.

Apps register typed handlers for arbitrary Meta webhook field values (e.g.
WhatsApp ``message_template_status_update`` or an Instagram extension field)
that the framework does not understand natively. A registration carries a
mandatory Pydantic parser plus an async handler — the parser converts the raw
``value`` dict from Meta into a typed model, and the handler receives a
:class:`CustomWebhook` whose ``parsed`` attribute holds that model.

The registry is built at the composition root (``wappa.platforms``) with each
installed Platform's ``builtin_fields``; a Platform without an entry cannot
register fields. Each Platform adapter receives the registry in its
constructor and builds a ``CustomWebhook`` for a registered field;
``WappaEventDispatcher`` then awaits the registered handler.

Built-in field values are reserved — apps cannot override native message,
identity, Calling, group, account, Coexistence, comment or mention contracts
through the registry.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import CustomWebhook


ParserFn = Callable[[dict[str, Any]], BaseModel]
HandlerFn = Callable[["CustomWebhook"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FieldHandler:
    """A single registered (field_name, parser, handler) triple."""

    field_name: str
    parser: ParserFn
    handler: HandlerFn
    platform: PlatformType


class FieldHandlerRegistry:
    """In-memory registry of custom webhook field handlers.

    ``builtin_fields`` maps each installed Platform to the field names its
    adapter handles natively; ``wappa.platforms.BUILTIN_FIELDS`` is the
    composition-root value.
    """

    def __init__(self, builtin_fields: Mapping[PlatformType, frozenset[str]]) -> None:
        self._builtin_fields = MappingProxyType(dict(builtin_fields))
        self._entries: dict[tuple[PlatformType, str], FieldHandler] = {}

    def register(
        self,
        field_name: str,
        *,
        parser: type[BaseModel] | ParserFn,
        handler: HandlerFn,
        platform: PlatformType = PlatformType.WHATSAPP,
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

        builtin = self._builtin_fields.get(platform)
        if builtin is None:
            raise ValueError(
                f"Webhook field registration is not available for {platform.value}"
            )
        if field_name in builtin:
            raise ValueError(
                f"Cannot register built-in webhook field '{field_name}' — "
                "it is handled by the framework."
            )
        if (platform, field_name) in self._entries:
            raise ValueError(f"Webhook field '{field_name}' is already registered.")

        parser_fn = self._coerce_parser(field_name, parser)

        if not inspect.iscoroutinefunction(handler):
            raise TypeError(
                f"Handler for '{field_name}' must be an async function "
                f"(got {type(handler).__name__})."
            )

        self._entries[(platform, field_name)] = FieldHandler(
            field_name=field_name, parser=parser_fn, handler=handler, platform=platform
        )

    def get(self, field_name: str, platform: PlatformType) -> FieldHandler | None:
        return self._entries.get((platform, field_name))

    def fields(self, platform: PlatformType) -> frozenset[str]:
        """Snapshot of registered field names for one Platform."""
        return frozenset(name for (p, name) in self._entries if p is platform)

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _coerce_parser(field_name: str, parser: type[BaseModel] | ParserFn) -> ParserFn:
        if isinstance(parser, type) and issubclass(parser, BaseModel):
            model_cls = parser

            def parse_model(raw: dict[str, Any]) -> BaseModel:
                return model_cls.model_validate(raw)

            return parse_model
        if callable(parser):
            return cast(ParserFn, parser)
        raise TypeError(
            f"Parser for '{field_name}' must be a Pydantic BaseModel subclass "
            f"or a callable returning a BaseModel (got {type(parser).__name__})."
        )
