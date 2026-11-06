"""Cloud API payloads for contacts, locations and location requests.

Pure builders (no I/O): the validation that precedes them stays with the
send in ``messenger/specialized.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wappa.domain.contacts import ContactCard
from wappa.schemas.core.recipient import apply_recipient_to_payload


def _copy_optional(src: Any, dst: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Copy truthy optional attrs from a pydantic model into a dict payload."""
    for field in fields:
        value = getattr(src, field, None)
        if value:
            dst[field] = value


def build_payload(
    recipient: str,
    message_type: str,
    message_data: dict[str, Any] | list[dict[str, Any]],
    *,
    reply_to_message_id: str | None = None,
    include_recipient_type: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "type": message_type,
    }
    if include_recipient_type:
        payload["recipient_type"] = "individual"
    payload[message_type] = message_data
    apply_recipient_to_payload(payload, recipient)
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}
    return payload


def location_data(
    latitude: float, longitude: float, name: str | None, address: str | None
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "latitude": str(latitude),
        "longitude": str(longitude),
    }
    if name:
        data["name"] = name
    if address:
        data["address"] = address
    return data


def location_request_data(body: str) -> dict[str, Any]:
    return {
        "type": "location_request_message",
        "body": {"text": body},
        "action": {"name": "send_location"},
    }


def contacts_data(contacts: Sequence[ContactCard]) -> list[dict[str, Any]]:
    return [convert_contact_to_api_format(c) for c in contacts]


def convert_contact_to_api_format(contact: ContactCard) -> dict[str, Any]:
    name_dict: dict[str, Any] = {"formatted_name": contact.name.formatted_name}
    _copy_optional(
        contact.name,
        name_dict,
        ("first_name", "last_name", "middle_name", "suffix", "prefix"),
    )

    api_contact: dict[str, Any] = {"name": name_dict}

    if contact.phones:
        phones: list[dict[str, Any]] = []
        for phone in contact.phones:
            phone_dict: dict[str, Any] = {"phone": phone.phone}
            _copy_optional(phone, phone_dict, ("type", "wa_id"))
            phones.append(phone_dict)
        api_contact["phones"] = phones

    if contact.emails:
        emails: list[dict[str, Any]] = []
        for email in contact.emails:
            email_dict: dict[str, Any] = {"email": email.email}
            _copy_optional(email, email_dict, ("type",))
            emails.append(email_dict)
        api_contact["emails"] = emails

    if contact.addresses:
        addresses: list[dict[str, Any]] = []
        address_fields = (
            "type",
            "street",
            "city",
            "state",
            "zip",
            "country",
            "country_code",
        )
        for address in contact.addresses:
            address_dict: dict[str, Any] = {}
            _copy_optional(address, address_dict, address_fields)
            addresses.append(address_dict)
        api_contact["addresses"] = addresses

    if contact.org:
        org_dict: dict[str, Any] = {}
        _copy_optional(contact.org, org_dict, ("company", "department", "title"))
        api_contact["org"] = org_dict

    if contact.urls:
        urls: list[dict[str, Any]] = []
        for url in contact.urls:
            url_dict: dict[str, Any] = {"url": url.url}
            _copy_optional(url, url_dict, ("type",))
            urls.append(url_dict)
        api_contact["urls"] = urls

    if contact.birthday:
        api_contact["birthday"] = contact.birthday

    return api_contact
