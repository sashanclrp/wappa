"""
Contract that external webhook integrations must satisfy to participate
in the Wappa gateway pipeline.
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

    Implementors parse raw HTTP requests into ExternalEvent instances,
    optionally resolve user identity, and declare their source name.

    Example:
        class MercadoPagoProcessor:
            def get_source_name(self) -> str:
                return "mercadopago"

            async def parse_event(self, request, inbox_id):
                body = await request.json()
                validated = MPWebhookSchema.model_validate(body)
                return ExternalEvent(
                    source="mercadopago",
                    event_type=f"{validated.type}.{validated.action}",
                    inbox_id=inbox_id,
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

    def get_source_name(self) -> str:
        """Return the source identifier (e.g., 'mercadopago', 'stripe')."""
        ...

    async def parse_event(
        self,
        request: "Request",
        inbox_id: str,
    ) -> "ExternalEvent":
        """
        Parse a raw HTTP request into a typed ExternalEvent.

        Args:
            request: FastAPI Request object with raw webhook body
            inbox_id: Inbox identifier from URL path

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
        Optionally resolve a user identifier from the event payload.

        Returns None if identity cannot be determined or db is not configured.
        """
        ...
