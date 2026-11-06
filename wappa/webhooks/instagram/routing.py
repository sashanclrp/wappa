"""Authenticated Instagram batch admission by professional account Inbox.

Every entry is validated and its Inbox credentials resolved before any
delivery is returned; messaging events and ``changes`` items (comments,
Live comments, mentions, registered extension fields) become one delivery
each. Comment/mention authors never register or select an Inbox.
"""

from typing import Any

from pydantic import ValidationError

from wappa.core.inbound.platform_webhooks import (
    PayloadRoutingError,
    RoutedWebhookDelivery,
)
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.instagram.models import InstagramWebhook


async def route_instagram_payload(
    payload: dict[str, Any], resolver: IInboxCredentialResolver
) -> tuple[RoutedWebhookDelivery, ...]:
    """Validate every event and bind credentials before the runtime schedules any."""
    try:
        batch = InstagramWebhook.model_validate(payload)
    except ValidationError as exc:
        raise PayloadRoutingError("Invalid Instagram messaging envelope") from exc
    deliveries: list[RoutedWebhookDelivery] = []
    for entry in batch.entry:
        try:
            ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=entry.id)
        except ValueError as exc:
            raise PayloadRoutingError(
                "Invalid Instagram professional account ID"
            ) from exc
        # All identities must be checked even for events we do not yet implement.
        for event in entry.messaging:
            if event.sender.id != entry.id and event.recipient.id != entry.id:
                raise PayloadRoutingError(
                    "Instagram event does not address its entry account"
                )
            if event.read is not None and event.recipient.id != entry.id:
                raise PayloadRoutingError(
                    "Instagram read event must address the receiving Inbox"
                )
        credentials = await resolver.resolve_credentials(ref)
        if (
            credentials.inbox_ref != ref
            or credentials.account_ref.platform is not ref.platform
            or credentials.account_ref.platform_account_id != entry.id
        ):
            raise PayloadRoutingError(
                "Instagram credential professional account mismatch"
            )
        units: list[dict[str, Any]] = [
            {"messaging": [event.model_dump(mode="json", exclude_none=True)]}
            for event in entry.messaging
        ]
        # One change per delivery: comments, live_comments, mentions, extensions.
        units.extend(
            {"changes": [change.model_dump(mode="json", by_alias=True)]}
            for change in entry.changes
        )
        for unit_body in units:
            unit = {
                "object": "instagram",
                "entry": [{"id": entry.id, "time": entry.time, **unit_body}],
            }
            deliveries.append(
                RoutedWebhookDelivery(
                    inbox_ref=ref,
                    account_ref=credentials.account_ref,
                    credentials=credentials,
                    payload=unit,
                )
            )
    return tuple(deliveries)
