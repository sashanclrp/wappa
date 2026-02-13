"""
Enhanced WhatsApp Business API client with SOLID principles.

Key Design Decisions:
- phone_number_id IS the tenant_id (WhatsApp Business Account identifier)
- Pure dependency injection (no fallback session creation)
- Single responsibility for HTTP operations
- Proper error handling and logging
"""

from datetime import datetime, timezone
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
        self.__class__.last_activity = datetime.now(timezone.utc)

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

        try:
            if files:
                # Multipart form-data request
                headers = self._get_headers(
                    include_content_type=False
                )  # aiohttp sets Content-Type
                data = self.form_builder.build_form_data(payload, files)

                self.logger.debug(
                    f"Sending multipart request to {url} for tenant {self.tenant_id}"
                )
                self.logger.debug(f"Payload: {payload}")
                self.logger.debug(f"Files: {list(files.keys())}")

                async with self.session.post(
                    url, headers=headers, data=data
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()
                    self.logger.debug(f"Response: {response_data}")
                    return response_data
            else:
                # Standard JSON request
                headers = self._get_headers()

                self.logger.debug(
                    f"Sending JSON request to {url} for tenant {self.tenant_id}"
                )
                self.logger.debug(f"Payload: {payload}")

                async with self.session.post(
                    url, headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()
                    self.logger.debug(f"Response: {response_data}")
                    return response_data

        except aiohttp.ClientResponseError as http_err:
            # Enhanced error logging
            try:
                error_text = (
                    await response.text() if "response" in locals() else "No response"
                )
            except Exception:
                error_text = "Error reading response"

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
                self.logger.error(f"🚨 Response: {error_text}")
                self.logger.error(
                    "🚨 ACTION REQUIRED: Update WhatsApp access token in environment variables!"
                )
                self.logger.error("🚨" * 10)
            else:
                self.logger.error(
                    f"HTTP error for tenant {self.tenant_id}: {http_err.status} - {error_text}"
                )
                self.logger.debug(f"Failed URL: {url}")
                self.logger.debug(
                    f"Failed headers: {headers if 'headers' in locals() else 'N/A'}"
                )
            raise
        except Exception as err:
            self.logger.error(f"Unexpected error for tenant {self.tenant_id}: {err}")
            raise

    async def get_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send GET request to WhatsApp API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Optional query parameters

        Returns:
            JSON response from WhatsApp API

        Raises:
            aiohttp.ClientResponseError: For HTTP errors
            Exception: For other request failures
        """
        self._update_activity()
        url = self.url_builder.get_endpoint_url(endpoint)

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
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send DELETE request to WhatsApp API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Optional query parameters

        Returns:
            JSON response from WhatsApp API

        Raises:
            aiohttp.ClientResponseError: For HTTP errors
            Exception: For other request failures
        """
        self._update_activity()
        url = self.url_builder.get_endpoint_url(endpoint)

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
