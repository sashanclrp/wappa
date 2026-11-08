"""WhatsApp identity evidence through the shared phone/BSUID parser."""

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DeliveryAddresses
from wappa.domain.user_identity import UserIdentity
from wappa.schemas.core.recipient import (
    RecipientKind,
    is_bsuid_digit_echo,
    resolve_recipient,
)


def whatsapp_identity(
    inbox_ref: InboxRef, user_id: str, addresses: tuple[str, ...]
) -> UserIdentity:
    phone = bsuid = parent = None
    for value in (*addresses, user_id):
        try:
            resolved = resolve_recipient(value)
        except ValueError:
            continue  # a Host-owned User ID is not address evidence
        if resolved.kind is RecipientKind.PHONE_NUMBER:
            phone = phone or resolved.phone_number
        elif resolved.bsuid and ".ENT." in resolved.bsuid:
            parent = parent or resolved.bsuid
        else:
            bsuid = bsuid or resolved.bsuid
    if phone and is_bsuid_digit_echo(phone, bsuid, parent):
        phone = None
    return UserIdentity(
        inbox_ref=inbox_ref,
        user_id=user_id,
        addresses=DeliveryAddresses.of(*addresses),
        phone_number=phone,
        bsuid=bsuid,
        parent_bsuid=parent,
    )
