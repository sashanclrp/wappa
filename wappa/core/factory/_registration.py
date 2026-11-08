"""Registration and ``with_*`` setters of ``WappaBuilder``.

A mixin so ``wappa_builder.py`` keeps the plugin, hook and ``build`` core; every
method here is still a public ``WappaBuilder`` method.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel

from ...domain.inbox.ports import IInboxDirectorySource
from ...domain.inbox.routing import InboxRoutingMode
from ...domain.interfaces.identity_resolver import IIdentityResolver
from ...schemas.core.types import PlatformType
from ..config.meta_application import MetaApplicationConfig
from ..config.settings import settings
from ..events.field_registry import FieldHandlerRegistry
from ..messaging.pipeline import MessengerMiddleware, MiddlewareEntry
from .inbox_assembly import resolve_routing_mode

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import CustomWebhook


class _BuilderRegistrationMixin:
    """Builder state touched by the registration and ``with_*`` methods."""

    messenger_middleware: list[MiddlewareEntry]
    field_registry: FieldHandlerRegistry
    identity_resolver: IIdentityResolver | None
    inbox_directory_source: IInboxDirectorySource | None
    inbox_routing_mode: InboxRoutingMode | None
    meta_application_config: MetaApplicationConfig | None
    persistence_backend: str
    _webhook_callback_mounted: bool

    def add_messenger_middleware(
        self,
        middleware: MessengerMiddleware,
        priority: int = 50,
    ) -> Self:
        """
        Register middleware to apply to every outbound ``IMessenger`` call.

        The framework assembles a :class:`MessengerPipeline` per request and
        runs the registered middleware in priority order around the raw
        messenger send. Cross-cutting concerns (cache, SSE lifecycle, pub/sub
        notifications, retry, metrics, tracing) each live in a single
        middleware rather than in a copy-pasted wrapper class.

        Priority Convention (lower = closer to raw transport / inner):

        - 10: Reliability (retry, circuit-breaker)
        - 30: Domain notifications (pub/sub)
        - 50: Caching / persistence  **← downstream cache middleware goes here**
        - 70: Lifecycle events (SSE)
        - 90: Observability (metrics, tracing)

        The pipeline runs outer → inner on the way in, then inner → outer on
        the way out. So a higher-priority middleware publishes its post-hook
        *after* any lower-priority middleware has completed. This is how the
        framework guarantees "cache write finishes before SSE publishes":
        the cache middleware sits at priority 50, the SSE middleware sits at
        priority 70, and the SSE ``publish`` call only runs after the whole
        inner chain (including the cache write) returns.

        Args:
            middleware: ``MessengerMiddleware`` instance (app-scoped, shared).
            priority: Execution band; see table above. Default 50.

        Returns:
            Self for method chaining.

        Example::

            builder.add_messenger_middleware(
                CacheMessengerMiddleware(cache=redis_cache),
                priority=50,
            )
        """
        self.messenger_middleware.append((middleware, priority))
        return self

    def register_webhook_field(
        self,
        field_name: str,
        *,
        parser: type[BaseModel] | Callable[[dict[str, Any]], BaseModel],
        handler: Callable[[CustomWebhook], Awaitable[None]],
        platform: PlatformType,
    ) -> Self:
        """
        Register a typed handler for a non-built-in Meta webhook field.

        Built-in fields (``messages``, ``user_preferences``, ``user_id_update``)
        are handled by the framework via :class:`WappaEventHandler`. Any other
        Meta field value (e.g. ``message_template_status_update``,
        ``account_update``, ``phone_number_quality_update``) is rejected with
        a 400 unless registered here.

        The ``parser`` is mandatory — handlers always receive a typed
        Pydantic model via ``CustomWebhook.parsed`` so business logic never
        deals with raw dicts. Pass either a ``BaseModel`` subclass (the
        framework will call ``.model_validate``) or any callable that
        accepts the raw ``value`` dict and returns a ``BaseModel``.

        Args:
            field_name: Meta webhook field value to handle.
            parser: ``BaseModel`` subclass or callable producing one.
            handler: Async callable invoked with the resulting
                ``CustomWebhook``.
            platform: The Platform whose webhook carries the field; required,
                since a field name means nothing without its Platform.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If ``field_name`` collides with a built-in or is
                already registered.
            TypeError: If ``parser`` or ``handler`` are the wrong shape.

        Example::

            class TemplateStatusUpdate(BaseModel):
                event: str
                message_template_id: str
                message_template_name: str
                reason: str | None = None

            async def on_template_status(webhook: CustomWebhook) -> None:
                update: TemplateStatusUpdate = webhook.parsed
                ...

            builder.register_webhook_field(
                "message_template_status_update",
                parser=TemplateStatusUpdate,
                handler=on_template_status,
                platform=PlatformType.WHATSAPP,
            )
        """
        self.field_registry.register(
            field_name, parser=parser, handler=handler, platform=platform
        )
        return self

    def with_identity_resolver(self, resolver: IIdentityResolver) -> Self:
        """
        Register an :class:`IIdentityResolver` for cache scoping.

        The resolver maps transport recipients (e.g. WhatsApp phone numbers)
        to the canonical user id Wappa should use when scoping per-user
        caches such as template state. When omitted, Wappa uses the
        passthrough resolver (recipient used as ``user_id`` unchanged),
        preserving pre-0.6.1 behavior.

        Args:
            resolver: Application-provided identity resolver instance.

        Returns:
            Self for method chaining.

        Example::

            class CanonicalIdResolver(IIdentityResolver):
                async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
                    return await db.lookup_canonical_id(inbox_ref, recipient)

            builder.with_identity_resolver(CanonicalIdResolver())
        """
        self.identity_resolver = resolver
        return self

    def with_inbox_directory_source(self, source: IInboxDirectorySource) -> Self:
        """
        Register the Host's read-only Inbox Directory source.

        Explicit Inbox routing requires it; legacy routing rejects it. The
        source maps the Host's durable schema to Wappa's canonical records.
        Wappa constructs and runs the Inbox Directory itself.
        """
        self.inbox_directory_source = source
        return self

    def with_inbox_routing(self, mode: InboxRoutingMode | str) -> Self:
        """Select ``legacy`` (settings-backed single Inbox) or ``explicit`` routing."""
        self.inbox_routing_mode = resolve_routing_mode(mode, settings)
        return self

    def with_meta_application_config(self, config: MetaApplicationConfig) -> Self:
        """Supply the one Meta Application Configuration explicitly.

        Configuring it here while ``META_APP_SECRET`` or
        ``META_WEBHOOK_VERIFY_TOKEN`` is also set in the environment fails at
        build time; there is no precedence between the two sources.
        """
        self.meta_application_config = config
        return self

    def with_persistence_backend(self, cache_type: str) -> Self:
        """Name the Table Cache backend the Inbox Directory reuses."""
        self.persistence_backend = cache_type
        return self

    def mount_webhook_callback(self) -> Self:
        """Record that the Meta Platform callbacks will be served by this app."""
        self._webhook_callback_mounted = True
        return self
