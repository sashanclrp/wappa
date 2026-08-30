"""
WhatsApp messaging dependency injection.

Every Inbox-dependent capability derives from one ``InboxExecutionContext``
resolved per request. Dependencies never repeat the directory lookup and
never see a raw header.
"""

from collections.abc import Callable

from fastapi import Depends

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.api.dependencies.whatsapp_media_dependencies import (
    get_whatsapp_media_factory,
)
from wappa.domain.builders.message_builder import MessageBuilder
from wappa.domain.factories.media_factory import WhatsAppMediaFactory
from wappa.domain.factories.message_factory import WhatsAppMessageFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.messaging.whatsapp.services import WhatsAppTemplateInfoService


async def get_whatsapp_message_factory() -> WhatsAppMessageFactory:
    """Get WhatsApp message factory (local, no Inbox needed)."""
    return WhatsAppMessageFactory()


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


async def get_whatsapp_interactive_handler(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppInteractiveHandler:
    return WhatsAppInteractiveHandler(client=client, inbox_id=context.inbox_id)


async def get_whatsapp_template_handler(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppTemplateHandler:
    return WhatsAppTemplateHandler(client=client, inbox_id=context.inbox_id)


async def get_whatsapp_specialized_handler(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppSpecializedHandler:
    return WhatsAppSpecializedHandler(client=client, inbox_id=context.inbox_id)


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


async def get_whatsapp_messenger(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    client: WhatsAppClient = Depends(get_whatsapp_client),
    media_handler: WhatsAppMediaHandler = Depends(get_whatsapp_media_handler),
    interactive_handler: WhatsAppInteractiveHandler = Depends(
        get_whatsapp_interactive_handler
    ),
    template_handler: WhatsAppTemplateHandler = Depends(get_whatsapp_template_handler),
    specialized_handler: WhatsAppSpecializedHandler = Depends(
        get_whatsapp_specialized_handler
    ),
    message_factory: WhatsAppMessageFactory = Depends(get_whatsapp_message_factory),
    media_factory: WhatsAppMediaFactory = Depends(get_whatsapp_media_factory),
) -> IMessenger:
    """Unified WhatsApp messenger for the selected Inbox."""
    return WhatsAppMessenger(
        client=client,
        media_handler=media_handler,
        interactive_handler=interactive_handler,
        template_handler=template_handler,
        specialized_handler=specialized_handler,
        inbox_id=context.inbox_id,
        message_factory=message_factory,
        media_factory=media_factory,
    )


async def get_message_builder(
    factory: WhatsAppMessageFactory = Depends(get_whatsapp_message_factory),
) -> Callable[[str], MessageBuilder]:
    """Factory callable for fluent message construction."""

    def create_builder(recipient: str) -> MessageBuilder:
        return MessageBuilder(factory, recipient)

    return create_builder
