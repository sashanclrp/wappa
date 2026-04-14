"""Pydantic models for WhatsApp template management read operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplateByIdRequest(BaseModel):
    """Input schema for fetching a template directly by template ID."""

    template_id: str = Field(..., min_length=1, description="Template identifier")
    fields: str | None = Field(
        default=None,
        description="Optional Graph API fields projection",
    )


class TemplateByNameRequest(BaseModel):
    """Input schema for fetching templates by name from a WABA."""

    template_name: str = Field(..., min_length=1, description="Template name")
    fields: str | None = Field(
        default=None,
        description="Optional Graph API fields projection",
    )


class TemplateListRequest(BaseModel):
    """Input schema for listing templates from a WABA."""

    name: str | None = Field(
        default=None,
        description="Optional template name filter",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Optional page size",
    )
    after: str | None = Field(
        default=None,
        description="Optional cursor for the next page",
    )
    before: str | None = Field(
        default=None,
        description="Optional cursor for the previous page",
    )
    fields: str | None = Field(
        default=None,
        description="Optional Graph API fields projection",
    )


class TemplateButton(BaseModel):
    """Button definition returned by Meta for template button components."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Button type")
    text: str | None = Field(default=None, description="Button label")
    url: str | None = Field(default=None, description="Optional CTA URL")
    phone_number: str | None = Field(
        default=None,
        description="Optional phone number for phone buttons",
    )


class TemplateExample(BaseModel):
    """Template component example values returned by Meta."""

    model_config = ConfigDict(extra="allow")

    body_text: list[list[str]] | None = Field(
        default=None,
        description="Example body parameter substitutions",
    )
    header_text: list[str] | None = Field(
        default=None,
        description="Example header text substitutions",
    )


class TemplateComponent(BaseModel):
    """Component definition for a WhatsApp message template."""

    model_config = ConfigDict(extra="allow")

    type: Literal["HEADER", "BODY", "FOOTER", "BUTTONS"] | str = Field(
        ...,
        description="Template component type",
    )
    format: str | None = Field(
        default=None,
        description="Optional component format such as TEXT, IMAGE, VIDEO, DOCUMENT",
    )
    text: str | None = Field(default=None, description="Component text content")
    example: TemplateExample | None = Field(
        default=None,
        description="Optional example values returned by Meta",
    )
    buttons: list[TemplateButton] | None = Field(
        default=None,
        description="Optional buttons for BUTTONS components",
    )


class TemplateInfo(BaseModel):
    """Single WhatsApp template definition."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Template identifier")
    name: str = Field(..., description="Template name")
    language: str | None = Field(None, description="Template language code")
    status: str | None = Field(None, description="Template approval status")
    category: str | None = Field(None, description="Template category")
    previous_category: str | None = Field(
        default=None,
        description="Previous category when returned by Meta",
    )
    components: list[TemplateComponent] = Field(
        default_factory=list,
        description="Template component definitions returned by Meta",
    )


class TemplatePagingCursors(BaseModel):
    """Paging cursors returned by Meta list endpoints."""

    before: str | None = Field(default=None, description="Previous page cursor")
    after: str | None = Field(default=None, description="Next page cursor")


class TemplatePaging(BaseModel):
    """Paging container returned by Meta list endpoints."""

    cursors: TemplatePagingCursors | None = Field(
        default=None,
        description="Cursor metadata for pagination",
    )


class TemplateInfoListResponse(BaseModel):
    """List response for template queries on a WABA."""

    data: list[TemplateInfo] = Field(
        default_factory=list,
        description="Template results matching the query",
    )
    paging: TemplatePaging | None = Field(
        default=None,
        description="Paging information returned by Meta",
    )


class TemplateNamespaceResponse(BaseModel):
    """Namespace metadata for a WhatsApp Business Account."""

    id: str = Field(..., description="WhatsApp Business Account ID")
    message_template_namespace: str | None = Field(
        default=None,
        description="Message template namespace assigned to the WABA",
    )
