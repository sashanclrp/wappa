"""WhatsApp Cloud API URL shapes and payload transport for one phone number.

Every call goes through the shared Meta transport
(``wappa.messaging.meta.MetaGraphClient``, ADR-0029): outcome classification,
Meta error logging and rate limits live there. This client keeps WhatsApp's
URL shapes and multipart form and raises on failure, because the WhatsApp
handlers map exceptions to results: ``MetaGraphError`` (rejected or
indeterminate, with the classified ``GraphResponse``) or ``RateLimitedError``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from pydantic import SecretStr

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.identity import InboxRef
from wappa.messaging.meta.graph import MetaGraphClient


class WhatsAppUrlBuilder:
    """Builds URLs for WhatsApp Business API endpoints."""

    def __init__(self, base_url: str, api_version: str, phone_number_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.phone_number_id = phone_number_id

    def get_messages_url(self) -> str:
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"

    def get_marketing_messages_url(self) -> str:
        return (
            f"{self.base_url}/{self.api_version}/"
            f"{self.phone_number_id}/marketing_messages"
        )

    def get_media_url(self, media_id: str | None = None) -> str:
        if media_id:
            return f"{self.base_url}/{self.api_version}/{media_id}"
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/media"

    def get_endpoint_url(self, endpoint: str) -> str:
        return f"{self.base_url}/{self.api_version}/{endpoint}"


class WhatsAppManagementUrlBuilder:
    """Builds WABA-level URLs for WhatsApp management operations."""

    def __init__(self, base_url: str, api_version: str, business_account_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.business_account_id = business_account_id

    def get_template_by_id_url(self, template_id: str) -> str:
        return f"{self.base_url}/{self.api_version}/{template_id}"

    def get_templates_url(self) -> str:
        return (
            f"{self.base_url}/{self.api_version}/"
            f"{self.business_account_id}/message_templates"
        )

    def get_business_account_url(self) -> str:
        return f"{self.base_url}/{self.api_version}/{self.business_account_id}"


class WhatsAppFormDataBuilder:
    """Builds form data for WhatsApp multipart requests."""

    @staticmethod
    def build_form_data(
        payload: dict[str, Any], files: dict[str, Any]
    ) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
        data: dict[str, str] = {key: str(value) for key, value in payload.items()}

        file_fields: dict[str, tuple[str, bytes, str]] = {}
        for field_name, file_info in files.items():
            if not (isinstance(file_info, tuple) and len(file_info) == 3):
                raise ValueError(
                    f"Invalid file format for field '{field_name}'. "
                    f"Expected tuple (filename, file_handle, content_type)"
                )
            filename, file_handle, content_type = file_info
            file_content = (
                file_handle.read() if hasattr(file_handle, "read") else file_handle
            )
            file_fields[field_name] = (filename, file_content, content_type)

        return data, file_fields


class WhatsAppClient:
    """One phone number's Cloud API calls over the shared ``MetaGraphClient``."""

    def __init__(
        self,
        session: httpx.AsyncClient,
        access_token: str,
        phone_number_id: str,
        logger: Any | None = None,
        api_version: str = settings.api_version,
        base_url: str = settings.base_url,
    ):
        self.session = session
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.logger = logger or get_logger(__name__)

        self.url_builder = WhatsAppUrlBuilder(base_url, api_version, phone_number_id)
        self.form_builder = WhatsAppFormDataBuilder()
        self.graph = MetaGraphClient(
            inbox_ref=InboxRef.whatsapp(phone_number_id),
            access_token=SecretStr(access_token),
            session_provider=lambda: session,
            graph_api_version=api_version,
            graph_base_url=base_url,
        )

        self.logger.info(
            f"WhatsApp client initialized for inbox/phone_id: {self.phone_number_id}, "
            f"api_version: {api_version}"
        )

    @property
    def inbox_id(self) -> str:
        return self.phone_number_id

    async def post_request(
        self,
        payload: dict[str, Any],
        custom_url: str | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST JSON (or a multipart form with ``files``); the accepted body.

        Raises ``MetaGraphError`` or ``RateLimitedError``.
        """
        url = custom_url or self.url_builder.get_messages_url()
        self.logger.debug("POST %s for inbox %s: %s", url, self.inbox_id, payload)
        if files:
            form_data, form_files = self.form_builder.build_form_data(payload, files)
            return await self.graph.call(
                "POST",
                url,
                data=form_data,
                files=form_files,
                operation="WhatsApp upload",
            )
        return await self.graph.call(
            "POST", url, json=payload, operation=_operation(payload)
        )

    async def get_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        """GET; the accepted body. Raises ``MetaGraphError`` or ``RateLimitedError``."""
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")
        return await self.graph.call(
            "GET", url, params=params, operation="WhatsApp read"
        )

    async def delete_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        """DELETE; the accepted body. Raises ``MetaGraphError`` or ``RateLimitedError``."""
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")
        return await self.graph.call(
            "DELETE", url, params=params, operation="WhatsApp delete"
        )

    @asynccontextmanager
    async def stream_get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[httpx.Response]:
        """Stream media bytes from the URL ``get_media_info`` returned."""
        async with self.graph.stream(url, params) as response:
            yield response


def _operation(payload: dict[str, Any]) -> str:
    kind = payload.get("type")
    return f"WhatsApp {kind} send" if isinstance(kind, str) else "WhatsApp send"
