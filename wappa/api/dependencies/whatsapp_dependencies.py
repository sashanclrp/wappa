"""
WhatsApp messaging dependency injection.

Provides dependency injection for WhatsApp messaging services including
factory pattern, client management, and messenger implementations.
"""

from fastapi import Depends, Request

from wappa.api.dependencies.whatsapp_media_dependencies import (
    get_whatsapp_media_factory,
)
from wappa.api.utils.inbox_helpers import require_inbox_context
from wappa.core.logging.logger import get_logger
from wappa.domain.builders.message_builder import MessageBuilder
from wappa.domain.factories.media_factory import WhatsAppMediaFactory
from wappa.domain.factories.message_factory import WhatsAppMessageFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.services import SettingsInboxCredentialStore
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
    """Get WhatsApp message factory.

    Returns:
        WhatsAppMessageFactory instance for WhatsApp platform
    """
    return WhatsAppMessageFactory()


async def get_whatsapp_client(request: Request) -> WhatsAppClient:
    """Get configured WhatsApp client with inbox-specific credentials.

    Args:
        request: FastAPI request object containing HTTP session

    Returns:
        Configured WhatsApp client with persistent session and inbox credentials

    Raises:
        ValueError: If inbox credentials are invalid
    """
    session = request.app.state.http_session

    # Get inbox ID from context (set by webhook processing or API middleware)
    inbox_id = require_inbox_context()

    credential_store = SettingsInboxCredentialStore()

    if not await credential_store.validate_inbox(inbox_id):
        raise ValueError(f"Invalid or inactive inbox: {inbox_id}")

    credentials = await credential_store.get_credentials(inbox_id)
    logger = get_logger(__name__)

    return WhatsAppClient(
        session=session,
        access_token=credentials.access_token,
        phone_number_id=inbox_id,  # inbox_id IS the phone_number_id
        logger=logger,
    )


async def get_whatsapp_media_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppMediaHandler:
    """Get configured WhatsApp media handler with inbox-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp media handler for upload/download operations
    """
    inbox_id = require_inbox_context()
    return WhatsAppMediaHandler(client=client, inbox_id=inbox_id)


async def get_whatsapp_interactive_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppInteractiveHandler:
    """Get configured WhatsApp interactive handler with inbox-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp interactive handler for button/list/CTA operations
    """
    inbox_id = require_inbox_context()
    return WhatsAppInteractiveHandler(client=client, inbox_id=inbox_id)


async def get_whatsapp_template_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppTemplateHandler:
    """Get configured WhatsApp template handler with inbox-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp template handler for business template operations
    """
    inbox_id = require_inbox_context()
    return WhatsAppTemplateHandler(client=client, inbox_id=inbox_id)


async def get_whatsapp_specialized_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppSpecializedHandler:
    """Get configured WhatsApp specialized handler with inbox-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp specialized handler for contact and location operations
    """
    inbox_id = require_inbox_context()
    return WhatsAppSpecializedHandler(client=client, inbox_id=inbox_id)


async def get_whatsapp_template_info_service(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppTemplateInfoService:
    """Get configured WhatsApp template info service with WABA context."""
    inbox_id = require_inbox_context()
    credential_store = SettingsInboxCredentialStore()
    credentials = await credential_store.get_credentials(inbox_id)
    return WhatsAppTemplateInfoService(
        client=client,
        business_account_id=credentials.platform_account_id or "",
    )


async def get_whatsapp_messenger(
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
    """Get unified WhatsApp messenger implementation with complete functionality."""
    inbox_id = require_inbox_context()
    return WhatsAppMessenger(
        client=client,
        media_handler=media_handler,
        interactive_handler=interactive_handler,
        template_handler=template_handler,
        specialized_handler=specialized_handler,
        inbox_id=inbox_id,
        message_factory=message_factory,
        media_factory=media_factory,
    )


async def get_message_builder(
    factory: WhatsAppMessageFactory = Depends(get_whatsapp_message_factory),
) -> MessageBuilder:
    """Get message builder for fluent message construction.

    Args:
        factory: Message factory for creating platform-specific payloads

    Returns:
        MessageBuilder instance for fluent message construction

    Note: The recipient should be set when using the builder
    """

    # Return a builder factory function since recipient is set per message
    def create_builder(recipient: str) -> MessageBuilder:
        return MessageBuilder(factory, recipient)

    return create_builder
