"""
Cache dependency injection for Inbox-dependent API routes.

State Handler and Template state services read or mutate Inbox- and
User-scoped Wappa state, so they resolve the Inbox Execution Context first.
"""

from fastapi import Depends, Request

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.api.services.handler_state_service import HandlerStateService
from wappa.api.services.template_state_service import TemplateStateService
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.domain.interfaces.identity_resolver import IIdentityResolver
from wappa.persistence.cache_factory import create_cache_factory


def build_cache_factory(
    request: Request,
    context: InboxExecutionContext,
    recipient: str | None = None,
) -> ICacheFactory:
    """Create an Inbox-scoped cache factory for an API route.

    For API routes (unlike webhooks) the user is the message recipient; a
    placeholder is used until the service learns the recipient.
    """
    cache_type = getattr(request.app.state, "wappa_cache_type", "memory")
    factory_class = create_cache_factory(cache_type)
    return factory_class(
        inbox_id=context.inbox_ref.cache_namespace,
        user_id=recipient or "api-route",
    )


def _get_identity_resolver(request: Request) -> IIdentityResolver | None:
    return getattr(request.app.state, "identity_resolver", None)


async def get_template_state_service(
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> TemplateStateService:
    cache_factory = build_cache_factory(request, context, recipient="template-api")
    return TemplateStateService(
        cache_factory, identity_resolver=_get_identity_resolver(request)
    )


async def get_handler_state_service(
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> HandlerStateService:
    cache_factory = build_cache_factory(request, context, recipient="handler-api")
    return HandlerStateService(
        cache_factory, identity_resolver=_get_identity_resolver(request)
    )
