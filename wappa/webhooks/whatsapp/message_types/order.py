"""
WhatsApp order message schema.

This module contains Pydantic models for processing WhatsApp order messages,
which are sent when users order products via catalog, single-, or multi-product messages.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import MessageContext


class OrderProductItem(BaseModel):
    """Individual product item in an order."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_retailer_id: str = Field(..., description="Product ID from the catalog")
    quantity: int = Field(..., description="Quantity of this product ordered", ge=1)
    item_price: float = Field(..., description="Individual product price", ge=0)
    currency: str = Field(..., description="Currency code (e.g., 'USD', 'EUR')")

    @field_validator("product_retailer_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        """Validate product ID is not empty."""
        if not v.strip():
            raise ValueError("Product retailer ID cannot be empty")
        return v.strip()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code format."""
        currency = v.strip().upper()
        if len(currency) != 3:
            raise ValueError("Currency code must be 3 characters (e.g., USD, EUR)")
        return currency

    @property
    def total_price(self) -> float:
        """Calculate total price for this item (quantity * price)."""
        return self.quantity * self.item_price


class OrderContent(BaseModel):
    """Order message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., description="Product catalog ID")
    text: str | None = Field(None, description="Text accompanying the order (optional)")
    product_items: list[OrderProductItem] = Field(
        ..., description="List of products in the order"
    )

    @field_validator("catalog_id")
    @classmethod
    def validate_catalog_id(cls, v: str) -> str:
        """Validate catalog ID is not empty."""
        if not v.strip():
            raise ValueError("Catalog ID cannot be empty")
        return v.strip()

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str | None) -> str | None:
        """Validate order text if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 1000:  # Reasonable order text limit
                raise ValueError("Order text cannot exceed 1000 characters")
        return v

    @field_validator("product_items")
    @classmethod
    def validate_product_items(
        cls, v: list[OrderProductItem]
    ) -> list[OrderProductItem]:
        """Validate product items list."""
        if not v or len(v) == 0:
            raise ValueError("Order must contain at least one product item")
        if len(v) > 50:  # Reasonable limit for order size
            raise ValueError("Order cannot contain more than 50 product items")

        # Check for duplicate products
        product_ids = [item.product_retailer_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Order cannot contain duplicate products")

        return v

    @property
    def item_count(self) -> int:
        """Get total number of items in the order."""
        return sum(item.quantity for item in self.product_items)

    @property
    def unique_products(self) -> int:
        """Get number of unique products in the order."""
        return len(self.product_items)

    def get_total_amount(self) -> float:
        """Calculate total order amount."""
        return sum(item.total_price for item in self.product_items)

    def get_currencies(self) -> set[str]:
        """Get all currencies used in the order."""
        return {item.currency for item in self.product_items}


class WhatsAppOrderMessage(BaseMessage):
    """
    WhatsApp order message model.

    Represents customer orders placed via catalog, single-product, or multi-product messages.
    Contains product details, quantities, prices, and optional order text.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
    from_: str = Field(
        default="",
        alias="from",
        description="WhatsApp user phone number (may be empty for username-only users)",
    )
    from_bsuid: str | None = Field(
        None,
        alias="from_user_id",
        description="Business Scoped User ID (BSUID) - stable identifier from webhook",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["order"] = Field(
        ..., description="Message type, always 'order' for order messages"
    )

    # Order content
    order: OrderContent = Field(
        ..., description="Order details including products and pricing"
    )

    # Context field
    context: MessageContext | None = Field(
        None, description="Context for order messages"
    )

    @property
    def sender_id(self) -> str:
        """Get the recommended sender identifier (BSUID if available, else phone)."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        """Check if this message has a BSUID set."""
        return bool(self.from_bsuid and self.from_bsuid.strip())

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate WhatsApp message ID format."""
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate Unix timestamp format."""
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        # Validate reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(v)
        if timestamp_int < 1577836800 or timestamp_int > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def catalog_id(self) -> str:
        """Get the product catalog ID."""
        return self.order.catalog_id

    @property
    def order_text(self) -> str | None:
        """Get the order text."""
        return self.order.text

    @property
    def has_order_text(self) -> bool:
        """Check if the order has accompanying text."""
        return self.order.text is not None and len(self.order.text.strip()) > 0

    @property
    def total_amount(self) -> float:
        """Get the total order amount."""
        return self.order.get_total_amount()

    @property
    def item_count(self) -> int:
        """Get total number of items in the order."""
        return self.order.item_count

    @property
    def unique_products(self) -> int:
        """Get number of unique products in the order."""
        return self.order.unique_products

    @property
    def currencies(self) -> set[str]:
        """Get all currencies used in the order."""
        return self.order.get_currencies()

    @property
    def is_multi_currency(self) -> bool:
        """Check if the order uses multiple currencies."""
        return len(self.currencies) > 1

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_products(self) -> list[OrderProductItem]:
        """Get the list of products in the order."""
        return self.order.product_items

    def get_product_by_id(self, product_id: str) -> OrderProductItem | None:
        """Get a specific product by its ID."""
        for item in self.order.product_items:
            if item.product_retailer_id == product_id:
                return item
        return None

    def get_total_by_currency(self) -> dict[str, float]:
        """Get total amounts grouped by currency."""
        totals = {}
        for item in self.order.product_items:
            if item.currency not in totals:
                totals[item.currency] = 0
            totals[item.currency] += item.total_price
        return totals

    def to_summary_dict(self) -> dict[str, str | bool | int | float | list]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "catalog_id": self.catalog_id,
            "total_amount": self.total_amount,
            "item_count": self.item_count,
            "unique_products": self.unique_products,
            "currencies": list(self.currencies),
            "is_multi_currency": self.is_multi_currency,
            "has_order_text": self.has_order_text,
            "product_ids": [
                item.product_retailer_id for item in self.order.product_items
            ],
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.ORDER

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        return {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "catalog_id": self.catalog_id,
            "total_amount": self.total_amount,
            "item_count": self.item_count,
            "unique_products": self.unique_products,
            "currencies": list(self.currencies),
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "order_content": self.order.model_dump(),
                "context": self.context.model_dump() if self.context else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "order_content": self.order.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "order_summary": {
                "catalog_id": self.catalog_id,
                "total_amount": self.total_amount,
                "item_count": self.item_count,
                "currencies": list(self.currencies),
                "is_multi_currency": self.is_multi_currency,
                "total_by_currency": self.get_total_by_currency(),
            },
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppOrderMessage":
        return cls.model_validate(data)
