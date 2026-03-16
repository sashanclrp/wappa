"""
External webhook processor interface.

Defines the contract that external webhook integrations must implement
to participate in the Wappa gateway pipeline.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.domain.events.external_event import ExternalEvent


class IWebhookProcessor(Protocol):
    """
    Interface for external webhook processors.

    Implementors parse raw HTTP requests into typed ExternalEvent instances,
    optionally resolve user identity from event payload, and identify
    the provider name.

    Example:
        class MercadoPagoProcessor:
            def get_provider_name(self) -> str:
                return "mercadopago"

            async def parse_event(self, request, tenant_id):
                body = await request.json()
                validated = MPWebhookSchema.model_validate(body)
                return ExternalEvent(
                    source="mercadopago",
                    event_type=f"{validated.type}.{validated.action}",
                    tenant_id=tenant_id,
                    payload=validated.model_dump(),
                    raw_data=body,
                )

            async def resolve_user_id(self, event, db):
                if not db:
                    return None
                async with db() as session:
                    sub = await get_subscription(session, event.payload["id"])
                    return sub.user_phone if sub else None
    """

    def get_provider_name(self) -> str:
        """Return the provider identifier (e.g., 'mercadopago', 'stripe')."""
        ...

    async def parse_event(
        self,
        request: "Request",
        tenant_id: str,
    ) -> "ExternalEvent":
        """
        Parse raw HTTP request into a typed ExternalEvent.

        Args:
            request: FastAPI Request object with raw webhook body
            tenant_id: Tenant identifier from URL path

        Returns:
            Validated ExternalEvent instance

        Raises:
            ValueError: If webhook payload is invalid or signature fails
        """
        ...

    async def resolve_user_id(
        self,
        event: "ExternalEvent",
        db: "Callable[[], AbstractAsyncContextManager[AsyncSession]] | None",
    ) -> str | None:
        """
        Optionally resolve user identity from event payload.

        Args:
            event: The parsed ExternalEvent
            db: Database session factory (None if DB plugin not configured)

        Returns:
            User identifier (e.g., phone number) or None if unresolvable
        """
        ...
