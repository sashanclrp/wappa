import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger


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
    """WhatsApp Business API client with dependency-injected httpx session.

    phone_number_id serves as the tenant identifier.
    """

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
        self.last_activity: datetime | None = None

        self.url_builder = WhatsAppUrlBuilder(base_url, api_version, phone_number_id)
        self.form_builder = WhatsAppFormDataBuilder()

        self.logger.info(
            f"WhatsApp client initialized for tenant/phone_id: {self.phone_number_id}, "
            f"api_version: {api_version}"
        )

    @property
    def tenant_id(self) -> str:
        return self.phone_number_id

    def _get_headers(self, include_content_type: bool = True) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _update_activity(self) -> None:
        self.last_activity = datetime.now(UTC)

    def _mask_headers(self, headers: dict[str, str]) -> dict[str, str]:
        masked = dict(headers)
        authorization = masked.get("Authorization")
        if authorization:
            parts = authorization.split(" ", 1)
            token = parts[1] if len(parts) == 2 else parts[0]
            token = f"{token[:8]}...{token[-4:]}" if len(token) > 10 else "***"
            masked["Authorization"] = (
                f"{parts[0]} {token}" if len(parts) == 2 else token
            )
        return masked

    def _parse_response_text(self, response_text: str) -> dict[str, Any] | None:
        if not response_text:
            return None
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    def _extract_meta_error_summary(
        self, response_payload: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if not isinstance(response_payload, dict):
            return None
        error = response_payload.get("error")
        if not isinstance(error, dict):
            return None

        summary = {
            "message": error.get("message"),
            "type": error.get("type"),
            "code": error.get("code"),
            "error_subcode": error.get("error_subcode"),
            "fbtrace_id": error.get("fbtrace_id"),
        }

        error_data = error.get("error_data")
        if isinstance(error_data, dict) and error_data.get("details"):
            summary["details"] = error_data["details"]

        return {key: value for key, value in summary.items() if value is not None}

    def _log_outbound_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> None:
        self.logger.debug("%s request to %s for tenant %s", method, url, self.tenant_id)
        self.logger.debug("Headers: %s", self._mask_headers(headers))

        if payload is not None:
            self.logger.debug("Payload: %s", payload)
            if "to" in payload:
                self.logger.debug("Recipient routing: to=%s", payload["to"])
            elif "recipient" in payload:
                self.logger.debug(
                    "Recipient routing: recipient=%s", payload["recipient"]
                )

        if files is not None:
            self.logger.debug("Files: %s", list(files.keys()))

    def _log_http_error(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        status: int,
        payload: dict[str, Any] | None = None,
        response_text: str | None = None,
    ) -> None:
        response_payload = self._parse_response_text(response_text or "")
        meta_error = self._extract_meta_error_summary(response_payload)

        self.logger.error(
            "HTTP %s error for tenant %s: status=%s url=%s",
            method,
            self.tenant_id,
            status,
            url,
        )
        self.logger.debug("Failed headers: %s", self._mask_headers(headers))
        if payload is not None:
            self.logger.debug("Failed payload: %s", payload)
        if response_text:
            self.logger.error("Meta raw response: %s", response_text)
        if meta_error is not None:
            self.logger.error("Meta error summary: %s", meta_error)

    async def post_request(
        self,
        payload: dict[str, Any],
        custom_url: str | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._update_activity()
        url = custom_url or self.url_builder.get_messages_url()
        headers: dict[str, str] = {}
        response_text = ""

        try:
            if files:
                headers = self._get_headers(include_content_type=False)
                form_data, form_files = self.form_builder.build_form_data(
                    payload, files
                )
                self._log_outbound_request(
                    method="POST multipart",
                    url=url,
                    headers=headers,
                    payload=payload,
                    files=files,
                )
                response = await self.session.post(
                    url, headers=headers, data=form_data, files=form_files
                )
            else:
                headers = self._get_headers()
                self._log_outbound_request(
                    method="POST",
                    url=url,
                    headers=headers,
                    payload=payload,
                )
                response = await self.session.post(url, headers=headers, json=payload)

            response_text = response.text
            response.raise_for_status()
            response_data = self._parse_response_text(response_text) or {}
            self.logger.debug("Response: %s", response_data)
            return response_data

        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code == 401:
                self.logger.error(
                    "CRITICAL: WhatsApp access token expired or invalid for tenant %s "
                    "(401 Unauthorized). Token starts with: %s... URL: %s. "
                    "ACTION REQUIRED: Update the WhatsApp access token in environment variables.",
                    self.tenant_id,
                    self.access_token[:20],
                    url,
                )
            self._log_http_error(
                method="POST",
                url=url,
                headers=headers,
                status=http_err.response.status_code,
                payload=payload,
                response_text=response_text,
            )
            raise
        except Exception as err:
            self.logger.error("Unexpected error for tenant %s: %s", self.tenant_id, err)
            raise

    async def get_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        self._update_activity()
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")

        try:
            response = await self.session.get(
                url, headers=self._get_headers(), params=params
            )
            response.raise_for_status()
            response_data = response.json()
            self.logger.debug(
                "GET %s params=%s returned: %s", url, params, response_data
            )
            return response_data
        except httpx.HTTPStatusError as http_err:
            self.logger.error(
                "HTTP GET error for tenant %s: %s - %s",
                self.tenant_id,
                http_err,
                http_err.response.text,
            )
            raise
        except Exception as err:
            self.logger.error(
                "Unexpected GET error for tenant %s: %s", self.tenant_id, err
            )
            raise

    async def delete_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        self._update_activity()
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")

        try:
            response = await self.session.delete(
                url, headers=self._get_headers(), params=params
            )
            response.raise_for_status()
            response_data = response.json()
            self.logger.debug(
                "DELETE %s params=%s returned: %s", url, params, response_data
            )
            return response_data
        except httpx.HTTPStatusError as http_err:
            self.logger.error(
                "HTTP DELETE error for tenant %s: %s - %s",
                self.tenant_id,
                http_err,
                http_err.response.text,
            )
            raise
        except Exception as err:
            self.logger.error(
                "Unexpected DELETE error for tenant %s: %s", self.tenant_id, err
            )
            raise

    @asynccontextmanager
    async def stream_get(self, url: str, params: dict[str, Any] | None = None):
        self._update_activity()
        try:
            async with self.session.stream(
                "GET", url, headers=self._get_headers(), params=params
            ) as response:
                self.logger.debug(
                    "Streaming GET to %s. Status: %s", url, response.status_code
                )
                yield response
        except httpx.HTTPError as e:
            self.logger.error(
                "Streaming GET failed for tenant %s: %s", self.tenant_id, e
            )
            raise
