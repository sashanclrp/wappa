"""
Contract that external webhook integrations must satisfy to participate
in the Wappa gateway pipeline.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastapi import Request

    from wappa.domain.events.external_event import ExternalEvent


class IWebhookProcessor(Protocol):
    """
    Interface for external webhook processors.

    Implementors authenticate and parse raw HTTP requests into ExternalEvent
    instances, then declare their source name.

    Example:
        class MercadoPagoProcessor:
            def get_source_name(self) -> str:
                return "mercadopago"

            async def parse_event(self, request, webhook_id):
                body = await request.json()
                validated = MPWebhookSchema.model_validate(body)
                return ExternalEvent(
                    source="mercadopago",
                    event_type=f"{validated.type}.{validated.action}",
                    payload=validated.model_dump(),
                    raw_data=body,
                )
    """

    def get_source_name(self) -> str:
        """Return the source identifier (e.g., 'mercadopago', 'stripe')."""
        ...

    async def parse_event(
        self,
        request: "Request",
        webhook_id: str | None,
    ) -> "ExternalEvent":
        """
        Parse a raw HTTP request into a typed ExternalEvent.

        Args:
            request: FastAPI Request object with raw webhook body
            webhook_id: Optional opaque identifier from the webhook URL

        Returns:
            Validated ExternalEvent instance

        Raises:
            HTTPException: For an expected sender-facing authentication failure
            ValueError: If the webhook payload is invalid
        """
        ...
