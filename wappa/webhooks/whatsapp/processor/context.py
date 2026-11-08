"""Context extractors: User base, business, forward, referral and conversation data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa.domain.error_evidence import meta_error_evidence
from wappa.schemas.core.recipient import looks_like_bsuid, looks_like_phone_number
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        BusinessContextBase,
        ConversationBase,
        EntryReferral,
        ErrorDetailBase,
        ForwardContextBase,
        UserBase,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _ContextMixin(_ProcessorBase):
    """Context extractors: User base, business, forward, referral and conversation data."""

    def _create_user_base_from_contacts(
        self, webhook: WhatsAppWebhook, sender_id: str
    ) -> UserBase:
        from wappa.webhooks.core.webhook_interfaces import UserBase

        for contact in webhook.get_contacts():
            if contact.user_id == sender_id:
                return UserBase(
                    phone_number=getattr(contact, "wa_id", "") or "",
                    bsuid=getattr(contact, "bsuid", None),
                    parent_bsuid=getattr(contact, "parent_bsuid", None),
                    username=getattr(contact, "username", None),
                    country_code=getattr(contact, "country_code", None),
                    profile_name=contact.display_name,
                    identity_key_hash=getattr(contact, "identity_key_hash", None),
                )

        fallback_phone = sender_id if looks_like_phone_number(sender_id) else ""
        fallback_bsuid = sender_id if looks_like_bsuid(sender_id) else None
        return UserBase(
            phone_number=fallback_phone,
            bsuid=fallback_bsuid,
            parent_bsuid=None,
            username=None,
            country_code=None,
            profile_name=None,
            identity_key_hash=None,
        )

    def _create_status_user_from_contacts(
        self, webhook: WhatsAppWebhook, recipient_id: str
    ) -> UserBase | None:
        """Build status recipient data when Meta includes the contacts block."""
        contacts = webhook.get_contacts()
        if not contacts:
            return None
        return self._create_user_base_from_contacts(webhook, recipient_id)

    def _extract_business_context(
        self, message_data: dict[str, Any]
    ) -> BusinessContextBase | None:
        from wappa.webhooks.core.webhook_interfaces import BusinessContextBase

        context = message_data.get("context")
        if not context or not context.get("referred_product"):
            return None

        return BusinessContextBase(
            contextual_message_id=context.get("id", ""),
            business_phone_number=context.get("from", ""),
            catalog_id=context["referred_product"].get("catalog_id"),
            product_retailer_id=context["referred_product"].get("product_retailer_id"),
        )

    def _extract_forward_context(
        self, message_data: dict[str, Any]
    ) -> ForwardContextBase | None:
        from wappa.webhooks.core.webhook_interfaces import ForwardContextBase

        context = message_data.get("context")
        if not context:
            return None

        is_forwarded = context.get("forwarded", False)
        is_frequently_forwarded = context.get("frequently_forwarded", False)

        if not (is_forwarded or is_frequently_forwarded):
            return None

        return ForwardContextBase(
            is_forwarded=is_forwarded,
            is_frequently_forwarded=is_frequently_forwarded,
            forward_count=None,
            original_sender=None,
        )

    def _extract_entry_referral(
        self, message_data: dict[str, Any]
    ) -> EntryReferral | None:
        """Click-to-WhatsApp ``referral`` → the shared ``EntryReferral``."""
        from wappa.webhooks.core.webhook_interfaces import (
            EntryPointKind,
            EntryReferral,
        )

        referral = message_data.get("referral")
        if not referral:
            return None
        source_type = referral.get("source_type")
        kind = {"ad": EntryPointKind.AD, "post": EntryPointKind.POST}.get(
            source_type or "", EntryPointKind.OTHER
        )
        source_id = referral.get("source_id") or None
        return EntryReferral(
            kind=kind,
            source=source_type,
            ad_id=source_id if kind is EntryPointKind.AD else None,
            post_id=source_id if kind is EntryPointKind.POST else None,
            source_url=referral.get("source_url"),
            headline=referral.get("headline"),
            body=referral.get("body"),
            media_type=referral.get("media_type"),
            image_url=referral.get("image_url"),
            video_url=referral.get("video_url"),
            thumbnail_url=referral.get("thumbnail_url"),
            click_id=referral.get("ctwa_clid"),
            welcome_message_text=(referral.get("welcome_message") or {}).get("text"),
        )

    def _extract_conversation_context(
        self, status_data: Any
    ) -> ConversationBase | None:
        from wappa.webhooks.core.webhook_interfaces import ConversationBase

        conversation = getattr(status_data, "conversation", None)
        if not conversation:
            return None

        pricing = getattr(status_data, "pricing", None)
        origin = getattr(conversation, "origin", None)
        origin_type = getattr(origin, "type", None) if origin else None

        return ConversationBase(
            conversation_id=getattr(conversation, "id", ""),
            expiration_timestamp=getattr(conversation, "expiration_timestamp", None),
            category=origin_type,
            origin_type=origin_type,
            is_billable=getattr(pricing, "billable", None) if pricing else None,
            pricing_model=getattr(pricing, "pricing_model", None) if pricing else None,
            pricing_category=getattr(pricing, "category", None) if pricing else None,
            pricing_type=getattr(pricing, "type", None) if pricing else None,
            pricing_subtype=getattr(pricing, "subtype", None) if pricing else None,
        )

    def _extract_status_errors(self, status_data: Any) -> list[ErrorDetailBase] | None:
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase

        errors = getattr(status_data, "errors", None)
        if not errors:
            return None

        error_details = []
        for error in errors:
            error_data = getattr(error, "error_data", None)
            error_details.append(
                ErrorDetailBase(
                    error_code=getattr(error, "code", 0),
                    error_evidence=meta_error_evidence(
                        f"{error.code}/{error.error_subcode}"
                        if error.error_subcode is not None
                        else error.code
                    ),
                    error_title=getattr(error, "title", "Unknown error"),
                    error_message=getattr(error, "message", ""),
                    error_details=getattr(error_data, "details", None)
                    if error_data
                    else None,
                    documentation_url=getattr(error, "href", None),
                    error_type="delivery_failure",
                    occurred_at=datetime.now(UTC),
                )
            )

        return error_details
