"""Services for WhatsApp template management read operations."""

from typing import Any

from wappa.messaging.whatsapp.client import WhatsAppClient, WhatsAppManagementUrlBuilder
from wappa.messaging.whatsapp.models.template_info_models import (
    TemplateByIdRequest,
    TemplateByNameRequest,
    TemplateInfo,
    TemplateInfoListResponse,
    TemplateListRequest,
    TemplateNamespaceResponse,
)


class WhatsAppTemplateInfoService:
    """Read-only service for WABA-level template management operations."""

    def __init__(
        self,
        client: WhatsAppClient,
        business_account_id: str,
        logger: Any | None = None,
    ):
        """Initialize service with Graph API client and WABA context."""
        self.client = client
        self.business_account_id = business_account_id
        self.logger = logger or client.logger
        self.url_builder = WhatsAppManagementUrlBuilder(
            base_url=client.url_builder.base_url,
            api_version=client.url_builder.api_version,
            business_account_id=business_account_id,
        )

    async def get_template_by_id(self, request: TemplateByIdRequest) -> TemplateInfo:
        """Fetch a template directly by template ID."""
        params = {"fields": request.fields} if request.fields else None
        response = await self.client.get_request(
            custom_url=self.url_builder.get_template_by_id_url(request.template_id),
            params=params,
        )
        return TemplateInfo.model_validate(response)

    async def list_templates(
        self,
        request: TemplateListRequest,
    ) -> TemplateInfoListResponse:
        """List templates for the configured WABA with optional filters."""
        params: dict[str, Any] = {}
        if request.name:
            params["name"] = request.name
        if request.limit is not None:
            params["limit"] = request.limit
        if request.after:
            params["after"] = request.after
        if request.before:
            params["before"] = request.before
        if request.fields:
            params["fields"] = request.fields

        response = await self.client.get_request(
            custom_url=self.url_builder.get_templates_url(),
            params=params or None,
        )
        return TemplateInfoListResponse.model_validate(response)

    async def get_template_by_name(
        self, request: TemplateByNameRequest
    ) -> TemplateInfoListResponse:
        """Fetch templates by exact name using Meta's WABA query endpoint."""
        return await self.list_templates(
            TemplateListRequest(name=request.template_name, fields=request.fields)
        )

    async def get_template_namespace(self) -> TemplateNamespaceResponse:
        """Fetch the WABA message template namespace."""
        response = await self.client.get_request(
            custom_url=self.url_builder.get_business_account_url(),
            params={"fields": "message_template_namespace"},
        )
        return TemplateNamespaceResponse.model_validate(response)
