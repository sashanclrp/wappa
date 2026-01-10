"""
WhatsApp messaging dependency injection.

Provides dependency injection for WhatsApp messaging services including
factory pattern, client management, and messenger implementations.
"""

from fastapi import Depends, Request

from wappa.api.utils.tenant_helpers import require_tenant_context
from wappa.core.logging.logger import get_logger
from wappa.domain.builders.message_builder import MessageBuilder
from wappa.domain.factories.message_factory import (
    MessageFactory,
    WhatsAppMessageFactory,
)
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.services.tenant_credentials_service import TenantCredentialsService
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


async def get_whatsapp_message_factory() -> MessageFactory:
    """Get WhatsApp message factory.

    Returns:
        MessageFactory implementation for WhatsApp platform
    """
    return WhatsAppMessageFactory()


async def get_whatsapp_client(request: Request) -> WhatsAppClient:
    """Get configured WhatsApp client with tenant-specific credentials.

    Args:
        request: FastAPI request object containing HTTP session

    Returns:
        Configured WhatsApp client with persistent session and tenant credentials

    Raises:
        ValueError: If tenant credentials are invalid
    """
    # Get persistent HTTP session from app state (created in main.py lifespan)
    session = request.app.state.http_session

    # Get tenant ID from context (set by webhook processing or API middleware)
    tenant_id = require_tenant_context()

    # Get tenant-specific access token (future: from database)
    access_token = TenantCredentialsService.get_whatsapp_access_token(tenant_id)

    # Validate tenant
    if not TenantCredentialsService.validate_tenant(tenant_id):
        raise ValueError(f"Invalid or inactive tenant: {tenant_id}")

    # Create tenant-aware logger
    logger = get_logger(__name__)

    # Create WhatsApp client with dependency injection
    return WhatsAppClient(
        session=session,
        access_token=access_token,
        phone_number_id=tenant_id,  # tenant_id IS the phone_number_id
        logger=logger,
    )


async def get_whatsapp_media_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppMediaHandler:
    """Get configured WhatsApp media handler with tenant-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp media handler for upload/download operations
    """
    tenant_id = require_tenant_context()
    return WhatsAppMediaHandler(client=client, tenant_id=tenant_id)


async def get_whatsapp_interactive_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppInteractiveHandler:
    """Get configured WhatsApp interactive handler with tenant-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp interactive handler for button/list/CTA operations
    """
    tenant_id = require_tenant_context()
    return WhatsAppInteractiveHandler(client=client, tenant_id=tenant_id)


async def get_whatsapp_template_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppTemplateHandler:
    """Get configured WhatsApp template handler with tenant-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp template handler for business template operations
    """
    tenant_id = require_tenant_context()
    return WhatsAppTemplateHandler(client=client, tenant_id=tenant_id)


async def get_whatsapp_specialized_handler(
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> WhatsAppSpecializedHandler:
    """Get configured WhatsApp specialized handler with tenant-specific context.

    Args:
        client: Configured WhatsApp client with persistent session

    Returns:
        Configured WhatsApp specialized handler for contact and location operations
    """
    tenant_id = require_tenant_context()
    return WhatsAppSpecializedHandler(client=client, tenant_id=tenant_id)


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
) -> IMessenger:
    """Get unified WhatsApp messenger implementation with complete functionality.

    Args:
        client: Configured WhatsApp client
        media_handler: Configured media handler for upload operations
        interactive_handler: Configured interactive handler for button/list/CTA operations
        template_handler: Configured template handler for business template operations
        specialized_handler: Configured specialized handler for contact/location operations

    Returns:
        Complete IMessenger implementation for WhatsApp messaging (text + media + interactive + template + specialized)
    """
    tenant_id = require_tenant_context()
    return WhatsAppMessenger(
        client=client,
        media_handler=media_handler,
        interactive_handler=interactive_handler,
        template_handler=template_handler,
        specialized_handler=specialized_handler,
        tenant_id=tenant_id,
    )


async def get_message_builder(
    factory: MessageFactory = Depends(get_whatsapp_message_factory),
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
