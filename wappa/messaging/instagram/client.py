"""Instagram's Platform client: its paths and error wording over the Meta transport.

``InstagramClient`` mirrors ``WhatsAppClient``: each owns its Platform's URL
shapes and error wording, and both make every API call through the shared
``wappa.messaging.meta.MetaGraphClient`` (ADR-0029), which owns the HTTP
call, outcome classification, Meta error logging and rate limits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from wappa.domain.inbox.identity import InboxRef
from wappa.messaging.meta.graph import GraphResponse, MetaGraphClient

# Known Messenger-family error codes → short, credential-free explanations.
_KNOWN_ERRORS: dict[str, str] = {
    "10/2534022": "outside the allowed messaging window",
    "10/2018278": "outside the allowed messaging window",
    "10/2018108": "the user cannot receive messages right now",
    "10/1893063": "the account is temporarily restricted",
    "10/2018300": "another app controls this thread",
    "100/2534037": "another app controls this thread",
    "551": "the user is unavailable",
    "551/1545041": "the user is unavailable",
    "200/1545041": "the recipient is not available",
    "200/2534041": "the account owner disabled message access",
    "100/2534014": "no matching Instagram user for this recipient (IGSID required)",
    "100/2534015": "invalid message data",
    "100/2534025": "comment is not valid for a private reply (expired or used)",
    "100/2534029": "the business is blocked from Instagram messaging",
    "100/2018008": "the provider could not fetch the media URL",
    "100/2018047": "attachment type does not match the media",
    "100/2018109": "attachment exceeds the size limit",
    "100/2018294": "video upload timed out",
    "100/2018074": "invalid attachment_id",
    "100/33": "object does not exist or is not accessible",
    "190": "access token is invalid or expired",
    "613/2534040": "rate limit reached",
    "4": "application rate limit reached",
    "2534068": "multi-image sends are not enabled for this account",
}


def describe_error(code: str | None, fallback: str) -> str:
    if code is None:
        return fallback
    head = code.split("/", 1)[0]
    return _KNOWN_ERRORS.get(code) or _KNOWN_ERRORS.get(head) or fallback


class InstagramClient:
    """One Instagram professional account's Graph calls (Unified Login)."""

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        access_token: SecretStr,
        session_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str,
        graph_base_url: str,
    ) -> None:
        self.graph = MetaGraphClient(
            inbox_ref=inbox_ref,
            access_token=access_token,
            session_provider=session_provider,
            graph_api_version=graph_api_version,
            graph_base_url=graph_base_url,
            describe=describe_error,
        )

    @property
    def inbox_ref(self) -> InboxRef:
        return self.graph.inbox_ref

    @property
    def account_id(self) -> str:
        return self.graph.account_id

    @property
    def messages_path(self) -> str:
        """Send API: DMs, private replies and sender actions."""
        return f"{self.account_id}/messages"

    @property
    def attachments_path(self) -> str:
        """Attachment Upload API (reusable ``attachment_id``)."""
        return f"{self.account_id}/message_attachments"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        operation: str = "Instagram operation",
        timeout: float | None = None,
    ) -> GraphResponse:
        """One governed call through ``MetaGraphClient``; never raises for an outcome."""
        return await self.graph.request(
            method,
            path,
            json=json,
            params=params,
            data=data,
            files=files,
            operation=operation,
            timeout=timeout,
        )


__all__ = ["GraphResponse", "InstagramClient", "describe_error"]
