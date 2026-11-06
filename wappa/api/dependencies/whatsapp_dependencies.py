"""
WhatsApp messaging dependency injection.

Every Inbox-dependent capability derives from one ``InboxExecutionContext``
resolved per request. Dependencies never repeat the directory lookup and
never see a raw header.
"""

from fastapi import Depends

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.payload_builders import (
    WhatsAppMediaPayloadBuilder,
    WhatsAppMessagePayloadBuilder,
)
from wappa.messaging.whatsapp.services import WhatsAppTemplateInfoService


async def get_whatsapp_message_payloads() -> WhatsAppMessagePayloadBuilder:
    """WhatsApp text payload builder (local, no Inbox needed)."""
    return WhatsAppMessagePayloadBuilder()


async def get_whatsapp_media_payloads() -> WhatsAppMediaPayloadBuilder:
    """WhatsApp media payload builder (local, no Inbox needed)."""
    return WhatsAppMediaPayloadBuilder()


async def get_whatsapp_client(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> WhatsAppClient:
    """WhatsApp client for the selected Inbox Execution Context."""
    return context.whatsapp_client()


async def get_whatsapp_media_handler(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppMediaHandler:
    return WhatsAppMediaHandler(
        client=client,
        inbox_id=context.inbox_id,
        media_download_client=context.media_download_client_provider(),
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
