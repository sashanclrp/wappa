"""Dependencies of the WhatsApp extension router.

Everything here serves routes and services that exist only on WhatsApp
(limits, validators, Template info and Template state, ``/health``). The router mounts :func:`whatsapp_only` once, so
every route behind it answers 501 under another Platform's path; the client
is built here from the Inbox's resolved credentials, never in the shared
Inbox Execution Context.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from wappa.api.dependencies.cache_dependencies import (
    build_cache_factory,
    get_identity_resolver,
)
from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
    route_platform,
)
from wappa.core.logging.logger import get_logger
from wappa.messaging.whatsapp.capabilities.templates import (
    TemplateStateService,
    WhatsAppTemplateInfoService,
)
from wappa.messaging.whatsapp.client import WhatsAppClient
from wappa.messaging.whatsapp.payloads import (
    WhatsAppMediaPayloadBuilder,
    WhatsAppMessagePayloadBuilder,
)
from wappa.schemas.core.types import PlatformType


async def whatsapp_only(
    platform: Annotated[PlatformType, Depends(route_platform)],
) -> None:
    """Router dependency of the WhatsApp extension router: 501 off WhatsApp.

    The one Platform-name gate in the HTTP API. It reads only the path
    Platform, so a static route answers 501 under ``/api/instagram`` without
    resolving an Inbox. Shared routes gate on ``requires_capability`` instead.
    """
    if platform is not PlatformType.WHATSAPP:
        raise HTTPException(
            status_code=501,
            detail=f"{platform.value} does not provide this route (WhatsApp-only)",
        )


async def get_whatsapp_message_payloads() -> WhatsAppMessagePayloadBuilder:
    """WhatsApp text payload builder (local, no Inbox needed)."""
    return WhatsAppMessagePayloadBuilder()


async def get_whatsapp_media_payloads() -> WhatsAppMediaPayloadBuilder:
    """WhatsApp media payload builder (local, no Inbox needed)."""
    return WhatsAppMediaPayloadBuilder()


async def get_whatsapp_client(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> WhatsAppClient:
    """WhatsApp client for the selected Inbox's resolved credentials."""
    client_kwargs: dict[str, str] = {}
    if context.graph_api_version is not None:
        client_kwargs["api_version"] = context.graph_api_version
    if context.graph_base_url is not None:
        client_kwargs["base_url"] = context.graph_base_url
    return WhatsAppClient(
        session=context.session,
        access_token=context.credentials.access_token.get_secret_value(),
        phone_number_id=context.inbox_id,
        logger=get_logger("wappa.api.whatsapp"),
        **client_kwargs,
    )


async def get_whatsapp_template_info_service(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppTemplateInfoService:
    """Template info service whose WABA comes from the canonical Inbox record.

    Callers never supply a second WABA argument, so an Inbox and a foreign
    account cannot be paired.
    """
    return WhatsAppTemplateInfoService(
        client=client, business_account_id=context.platform_account_id
    )


async def get_template_state_service(
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> TemplateStateService:
    """Template state service scoped to the selected Inbox."""
    cache_factory = build_cache_factory(request, context, recipient="template-api")
    return TemplateStateService(
        cache_factory, identity_resolver=get_identity_resolver(request)
    )
