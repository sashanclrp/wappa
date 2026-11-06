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

from .errors import describe_error


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


__all__ = ["GraphResponse", "InstagramClient"]
