"""WhatsApp payload routing: authenticated Meta batch → qualified deliveries.

This module understands Meta's payload shape and maps its native identifiers
to Wappa references. It runs only after the callback body has been
authenticated. It resolves every Inbox through the internal credential
resolver, proves that each phone-scoped change belongs to the WABA in
``entry[].id``, and fans WABA-only changes out to every validated member.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from wappa.domain.inbox.errors import InboxMembershipError, InboxNotFoundError
from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials


class PayloadRoutingError(Exception):
    """An authenticated payload cannot identify a safe dispatch scope."""


class PlatformAccountNotRegisteredError(PayloadRoutingError):
    """A confirmed Platform Account has no active Inbox."""

    def __init__(self, account_ref: PlatformAccountRef) -> None:
        self.account_ref = account_ref
        super().__init__(
            f"No active Inbox is registered for Platform Account {account_ref}"
        )


@dataclass(frozen=True, slots=True)
class RoutedWebhookDelivery:
    """One Platform change bound to one validated Inbox."""

    inbox_ref: InboxRef
    account_ref: PlatformAccountRef
    credentials: ResolvedInboxCredentials
    payload: dict[str, Any]

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id


async def route_whatsapp_payload(
    payload: dict[str, Any],
    resolver: IInboxCredentialResolver,
) -> tuple[RoutedWebhookDelivery, ...]:
    """Split a Meta batch and bind each change to a validated Inbox.

    Phone-scoped changes use ``value.metadata.phone_number_id`` or a flat
    ``value.phone_number_id`` and must belong to the ``entry[].id`` WABA. A
    change without either identifier fans out to every active Inbox under
    that WABA. The WABA ID is never used as an Inbox ID.

    Raises:
        PayloadRoutingError: structurally unroutable payload (400).
        PlatformAccountNotRegisteredError: confirmed empty WABA (400).
        InboxNotFoundError: confirmed unknown or inactive Inbox (400).
        InboxMembershipError: phone Inbox belongs to another WABA (400).
        InboxDirectoryUnavailableError / InboxCredentialIntegrityError: 503.
    """
    if payload.get("object") != "whatsapp_business_account":
        raise PayloadRoutingError(
            "Expected a WhatsApp Business Account webhook payload"
        )

    entries = payload.get("entry")
    if not isinstance(entries, list) or not entries:
        raise PayloadRoutingError(
            "WhatsApp webhook payload must contain a non-empty entry array"
        )

    deliveries: list[RoutedWebhookDelivery] = []
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise PayloadRoutingError(
                f"WhatsApp webhook entry[{entry_index}] must be an object"
            )
        account_ref = _account_ref(entry.get("id"), entry_index)
        changes = entry.get("changes")
        if not isinstance(changes, list) or not changes:
            raise PayloadRoutingError(
                f"WhatsApp webhook entry[{entry_index}] must contain changes"
            )

        for change_index, change in enumerate(changes):
            if not isinstance(change, dict):
                raise PayloadRoutingError(
                    f"WhatsApp webhook entry[{entry_index}].changes[{change_index}] "
                    "must be an object"
                )
            value = change.get("value")
            if not isinstance(value, dict):
                raise PayloadRoutingError(
                    f"WhatsApp webhook entry[{entry_index}].changes[{change_index}]"
                    ".value must be an object"
                )
            value_waba_id = value.get("waba_id")
            if (
                value_waba_id is not None
                and value_waba_id != account_ref.platform_account_id
            ):
                raise PayloadRoutingError(
                    f"WhatsApp webhook WABA mismatch: entry id "
                    f"{account_ref.platform_account_id!r} does not match "
                    f"value.waba_id {value_waba_id!r}"
                )

            unit_entry = {**entry, "changes": [change]}
            unit_payload = {**payload, "entry": [unit_entry]}
            for inbox_ref, credentials in await _resolve_change_inboxes(
                value=value, account_ref=account_ref, resolver=resolver
            ):
                deliveries.append(
                    RoutedWebhookDelivery(
                        inbox_ref=inbox_ref,
                        account_ref=account_ref,
                        credentials=credentials,
                        payload=unit_payload,
                    )
                )

    return tuple(deliveries)


def _account_ref(raw: Any, entry_index: int) -> PlatformAccountRef:
    if not isinstance(raw, str) or not raw:
        raise PayloadRoutingError(
            f"WhatsApp webhook entry[{entry_index}].id must name a WABA"
        )
    try:
        return PlatformAccountRef.whatsapp(raw)
    except ValidationError as exc:
        raise PayloadRoutingError(
            f"WhatsApp webhook entry[{entry_index}].id is not a valid WABA identifier"
        ) from exc


def _phone_number_id(value: dict[str, Any]) -> str | None:
    metadata = value.get("metadata")
    metadata_id = (
        metadata.get("phone_number_id") if isinstance(metadata, dict) else None
    )
    flat_id = value.get("phone_number_id")
    if metadata_id is not None and flat_id is not None and metadata_id != flat_id:
        raise PayloadRoutingError(
            "WhatsApp webhook has conflicting metadata and flat phone_number_id values"
        )
    phone_number_id = metadata_id if metadata_id is not None else flat_id
    if phone_number_id is None:
        return None
    if not isinstance(phone_number_id, str) or not phone_number_id:
        raise PayloadRoutingError("WhatsApp phone_number_id must be a non-empty string")
    return phone_number_id


async def _resolve_change_inboxes(
    *,
    value: dict[str, Any],
    account_ref: PlatformAccountRef,
    resolver: IInboxCredentialResolver,
) -> tuple[tuple[InboxRef, ResolvedInboxCredentials], ...]:
    phone_number_id = _phone_number_id(value)
    if phone_number_id is not None:
        try:
            inbox_ref = InboxRef.whatsapp(phone_number_id)
        except ValidationError as exc:
            raise PayloadRoutingError(
                "WhatsApp phone_number_id is not a valid Inbox identifier"
            ) from exc
        credentials = await resolver.resolve_credentials(inbox_ref)
        if credentials.account_ref != account_ref:
            raise InboxMembershipError(inbox_ref, account_ref)
        return ((inbox_ref, credentials),)

    members = await resolver.list_inbox_refs_for_platform_account(account_ref)
    ordered = tuple(sorted(set(members)))
    if not ordered:
        raise PlatformAccountNotRegisteredError(account_ref)
    resolved: list[tuple[InboxRef, ResolvedInboxCredentials]] = []
    for inbox_ref in ordered:
        if inbox_ref.platform is not account_ref.platform:
            raise InboxMembershipError(inbox_ref, account_ref)
        try:
            credentials = await resolver.resolve_credentials(inbox_ref)
        except InboxNotFoundError as exc:
            raise InboxMembershipError(inbox_ref, account_ref) from exc
        if credentials.account_ref != account_ref:
            raise InboxMembershipError(inbox_ref, account_ref)
        resolved.append((inbox_ref, credentials))
    return tuple(resolved)


__all__ = [
    "PayloadRoutingError",
    "PlatformAccountNotRegisteredError",
    "RoutedWebhookDelivery",
    "route_whatsapp_payload",
]
