"""
Enhanced WhatsApp Business API client with SOLID principles.

Key Design Decisions:
- phone_number_id IS the tenant_id (WhatsApp Business Account identifier)
- Pure dependency injection (no fallback session creation)
- Single responsibility for HTTP operations
- Proper error handling and logging
"""

import json
from datetime import UTC, datetime
from typing import Any

import aiohttp

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger


class WhatsAppUrlBuilder:
    """Builds URLs for WhatsApp Business API endpoints."""

    def __init__(self, base_url: str, api_version: str, phone_number_id: str):
        """Initialize URL builder with configuration.

        Args:
            base_url: Facebook Graph API base URL
            api_version: WhatsApp API version
            phone_number_id: WhatsApp Business phone number ID (tenant identifier)
        """
        self.base_url = base_url.rstrip("/")  # Ensure no trailing slash
        self.api_version = api_version
        self.phone_number_id = phone_number_id

    def get_messages_url(self) -> str:
        """Build URL for sending messages."""
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"

    def get_media_url(self, media_id: str | None = None) -> str:
        """Build URL for media operations.

        Args:
            media_id: Optional media ID for specific media operations

        Returns:
            URL for media endpoint
        """
        if media_id:
            return f"{self.base_url}/{self.api_version}/{media_id}"
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/media"

    def get_endpoint_url(self, endpoint: str) -> str:
        """Build URL for any custom endpoint.

        Args:
            endpoint: API endpoint path

        Returns:
            Complete URL for the endpoint
        """
        return f"{self.base_url}/{self.api_version}/{endpoint}"


class WhatsAppManagementUrlBuilder:
    """Builds WABA-level URLs for WhatsApp management operations."""

    def __init__(self, base_url: str, api_version: str, business_account_id: str):
        """Initialize URL builder for WABA management endpoints."""
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.business_account_id = business_account_id

    def get_template_by_id_url(self, template_id: str) -> str:
        """Build URL for fetching a template directly by template ID."""
        return f"{self.base_url}/{self.api_version}/{template_id}"

    def get_templates_url(self) -> str:
        """Build URL for listing or filtering templates by WABA."""
        return (
            f"{self.base_url}/{self.api_version}/"
            f"{self.business_account_id}/message_templates"
        )

    def get_business_account_url(self) -> str:
        """Build URL for fetching WABA-level metadata."""
        return f"{self.base_url}/{self.api_version}/{self.business_account_id}"


class WhatsAppFormDataBuilder:
    """Builds form data for WhatsApp multipart requests."""

    @staticmethod
    def build_form_data(
        payload: dict[str, Any], files: dict[str, Any]
    ) -> aiohttp.FormData:
        """Build FormData for multipart/form-data requests.

        Args:
            payload: Data fields to include in the form
            files: Files to upload in format {field_name: (filename, file_handle, content_type)}

        Returns:
            aiohttp.FormData object ready for request

        Raises:
            ValueError: If file format is invalid
        """
        form = aiohttp.FormData()

        # Add data fields first (important for WhatsApp API)
        if payload:
            for key, value in payload.items():
                form.add_field(key, str(value))

        # Add files - WhatsApp expects specifically a 'file' field
        for field_name, file_info in files.items():
            if isinstance(file_info, tuple) and len(file_info) == 3:
                filename, file_handle, content_type = file_info

                # Read file content if it's a file-like object
                if hasattr(file_handle, "read"):
                    file_content = file_handle.read()
                else:
                    file_content = file_handle

                # Add file to FormData with explicit filename and content_type
                form.add_field(
                    field_name,
                    file_content,
                    filename=filename,
                    content_type=content_type,
                )
            else:
                raise ValueError(
                    f"Invalid file format for field '{field_name}'. "
                    f"Expected tuple (filename, file_handle, content_type)"
                )

        return form


class WhatsAppClient:
    """
    Enhanced WhatsApp Business API client with proper dependency injection.

    Key Design Decisions:
    - phone_number_id IS the tenant_id (WhatsApp Business Account identifier)
    - Pure dependency injection (no fallback session creation)
    - Single responsibility for HTTP operations
    - Proper error handling and logging
    """

    # Class-level activity tracking
    last_activity: datetime | None = None

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        phone_number_id: str,
        logger: Any | None = None,
        api_version: str = settings.api_version,
        base_url: str = settings.base_url,
    ):
        """Initialize WhatsApp client with dependency injection.

        Args:
            session: Persistent aiohttp session (managed by FastAPI lifespan)
            access_token: WhatsApp Business API access token for this tenant
            phone_number_id: WhatsApp Business phone number ID (serves as tenant_id)
            logger: Pre-configured logger instance
            api_version: WhatsApp API version to use
            base_url: Facebook Graph API base URL
        """
        self.session = session
        self.access_token = access_token
        self.phone_number_id = phone_number_id  # This IS the tenant identifier
        self.logger = logger or get_logger(__name__)

        # Initialize URL and form builders
        self.url_builder = WhatsAppUrlBuilder(base_url, api_version, phone_number_id)
        self.form_builder = WhatsAppFormDataBuilder()

        # Log initialization
        self.logger.info(
            f"WhatsApp client initialized for tenant/phone_id: {self.phone_number_id}, "
            f"api_version: {api_version}"
        )

    @property
    def tenant_id(self) -> str:
        """Get tenant ID (which is the phone_number_id).

        Note: In WhatsApp Business API, the phone_number_id IS the tenant identifier.
        """
        return self.phone_number_id

    def _get_headers(self, include_content_type: bool = True) -> dict[str, str]:
        """Get HTTP headers for WhatsApp API requests.

        Args:
            include_content_type: Whether to include Content-Type header

        Returns:
            Dictionary of HTTP headers
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self.__class__.last_activity = datetime.now(UTC)

    def _mask_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Return a log-safe copy of HTTP headers."""
        masked_headers = dict(headers)
        authorization = masked_headers.get("Authorization")
        if authorization:
            parts = authorization.split(" ", 1)
            token = parts[1] if len(parts) == 2 else parts[0]
            token = f"{token[:8]}...{token[-4:]}" if len(token) > 10 else "***"
            masked_headers["Authorization"] = (
                f"{parts[0]} {token}" if len(parts) == 2 else token
            )
        return masked_headers

    def _parse_response_text(self, response_text: str) -> dict[str, Any] | None:
        """Parse a JSON response body when possible."""
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
        """Extract the most useful fields from Meta's error envelope."""
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
        """Log outbound request details with safe redaction."""
        self.logger.debug(
            "%s request to %s for tenant %s",
            method,
            url,
            self.tenant_id,
        )
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
        """Log HTTP failures with the exact response body and Meta error fields."""
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
        """Send POST request to WhatsApp API.

        Args:
            payload: JSON payload for the request
            custom_url: Optional custom URL (defaults to messages endpoint)
            files: Optional files for multipart upload

        Returns:
            JSON response from WhatsApp API

        Raises:
            aiohttp.ClientResponseError: For HTTP errors
            Exception: For other request failures
        """
        self._update_activity()
        url = custom_url or self.url_builder.get_messages_url()
        headers: dict[str, str] = {}
        response_text = ""

        try:
            if files:
                # Multipart form-data request
                headers = self._get_headers(
                    include_content_type=False
                )  # aiohttp sets Content-Type
                data = self.form_builder.build_form_data(payload, files)

                self._log_outbound_request(
                    method="POST multipart",
                    url=url,
                    headers=headers,
                    payload=payload,
                    files=files,
                )

                async with self.session.post(
                    url, headers=headers, data=data
                ) as response:
                    response_text = await response.text()
                    response.raise_for_status()
                    response_data = self._parse_response_text(response_text) or {}
                    self.logger.debug("Response: %s", response_data)
                    return response_data
            else:
                # Standard JSON request
                headers = self._get_headers()

                self._log_outbound_request(
                    method="POST",
                    url=url,
                    headers=headers,
                    payload=payload,
                )

                async with self.session.post(
                    url, headers=headers, json=payload
                ) as response:
                    response_text = await response.text()
                    response.raise_for_status()
                    response_data = self._parse_response_text(response_text) or {}
                    self.logger.debug("Response: %s", response_data)
                    return response_data

        except aiohttp.ClientResponseError as http_err:
            # Special handling for authentication errors
            if http_err.status == 401:
                self.logger.error("🚨" * 10)
                self.logger.error(
                    "🚨 CRITICAL: WHATSAPP ACCESS TOKEN EXPIRED OR INVALID! 🚨"
                )
                self.logger.error(
                    f"🚨 Tenant {self.tenant_id} authentication FAILED - 401 Unauthorized"
                )
                self.logger.error(f"🚨 Token starts with: {self.access_token[:20]}...")
                self.logger.error(f"🚨 URL: {url}")
                self.logger.error(f"🚨 Response: {response_text or 'No response body'}")
                self.logger.error(
                    "🚨 ACTION REQUIRED: Update WhatsApp access token in environment variables!"
                )
                self.logger.error("🚨" * 10)
            self._log_http_error(
                method="POST",
                url=url,
                headers=headers,
                status=http_err.status,
                payload=payload,
                response_text=response_text,
            )
            raise
        except Exception as err:
            self.logger.error(f"Unexpected error for tenant {self.tenant_id}: {err}")
            raise

    async def get_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        """Send GET request to WhatsApp API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Optional query parameters
            custom_url: Optional full URL override

        Returns:
            JSON response from WhatsApp API

        Raises:
            aiohttp.ClientResponseError: For HTTP errors
            Exception: For other request failures
        """
        self._update_activity()
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")

        try:
            async with self.session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                response.raise_for_status()
                response_data = await response.json()
                self.logger.debug(
                    f"GET request to {url} with params: {params} returned: {response_data}"
                )
                return response_data

        except aiohttp.ClientResponseError as http_err:
            try:
                error_text = (
                    await response.text() if "response" in locals() else "No response"
                )
            except Exception:
                error_text = "Error reading response"
            self.logger.error(
                f"HTTP GET error for tenant {self.tenant_id}: {http_err} - {error_text}"
            )
            raise
        except Exception as err:
            self.logger.error(
                f"Unexpected GET error for tenant {self.tenant_id}: {err}"
            )
            raise

    async def delete_request(
        self,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        """Send DELETE request to WhatsApp API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Optional query parameters
            custom_url: Optional full URL override

        Returns:
            JSON response from WhatsApp API

        Raises:
            aiohttp.ClientResponseError: For HTTP errors
            Exception: For other request failures
        """
        self._update_activity()
        url = custom_url or self.url_builder.get_endpoint_url(endpoint or "")

        try:
            async with self.session.delete(
                url, headers=self._get_headers(), params=params
            ) as response:
                response.raise_for_status()
                response_data = await response.json()
                self.logger.debug(
                    f"DELETE request to {url} with params: {params} returned: {response_data}"
                )
                return response_data

        except aiohttp.ClientResponseError as http_err:
            try:
                error_text = (
                    await response.text() if "response" in locals() else "No response"
                )
            except Exception:
                error_text = "Error reading response"
            self.logger.error(
                f"HTTP DELETE error for tenant {self.tenant_id}: {http_err} - {error_text}"
            )
            raise
        except Exception as err:
            self.logger.error(
                f"Unexpected DELETE error for tenant {self.tenant_id}: {err}"
            )
            raise

    async def get_request_stream(
        self, url: str, params: dict[str, Any] | None = None
    ) -> tuple[aiohttp.ClientSession, aiohttp.ClientResponse]:
        """Perform streaming GET request.

        Returns both session and response for streaming. Caller is responsible
        for managing the response lifecycle.

        Args:
            url: Full URL to request (e.g., direct media URL)
            params: Optional query parameters

        Returns:
            Tuple of (session, response) for streaming

        Raises:
            aiohttp.ClientError: For HTTP request failures
        """
        self._update_activity()

        try:
            response = await self.session.get(
                url, headers=self._get_headers(), params=params
            )
            self.logger.debug(
                f"Streaming GET request to {url} started. Status: {response.status}"
            )
            return self.session, response

        except aiohttp.ClientError as e:
            self.logger.error(
                f"Streaming GET request failed for tenant {self.tenant_id}: {e}"
            )
            raise
