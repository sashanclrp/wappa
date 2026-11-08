"""Typed snapshots of the structure carried by one actual Platform message.

These are evidence values, not send inputs: adapters record the wire's visible
structure after emulation, folding, media selection and upload.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from wappa.domain.contacts import ContactCard


class _ContentValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PartMedia(_ContentValue):
    type: str
    id: str | None = None
    url: str | None = None
    filename: str | None = None
    voice: bool | None = None
    reusable: bool | None = None

    @model_validator(mode="after")
    def _one_reference(self) -> Self:
        if (self.id is None) == (self.url is None):
            raise ValueError("Media evidence requires exactly one id or url")
        return self


class PartButton(_ContentValue):
    type: Literal["reply", "url"]
    title: str | None = None
    id: str | None = None
    url: str | None = None


class PartQuickReply(_ContentValue):
    type: str
    title: str | None = None
    id: str | None = None
    image_url: str | None = None


class PartHeader(_ContentValue):
    text: str | None = None
    media: PartMedia | None = None


class PartElement(_ContentValue):
    title: str
    subtitle: str | None = None
    media: PartMedia | None = None
    buttons: tuple[PartButton, ...] = ()
    default_action: PartButton | None = None


class PartRow(_ContentValue):
    id: str
    title: str
    description: str | None = None


class PartSection(_ContentValue):
    title: str | None = None
    rows: tuple[PartRow, ...]


class PartLocation(_ContentValue):
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


class PartTemplateComponent(_ContentValue):
    type: str
    sub_type: str | None = None
    index: str | int | None = None
    # Native Template parameter values are evidence, never rendered text.
    parameters: tuple[JsonValue, ...] = ()


class PartTemplate(_ContentValue):
    name: str
    language: str
    components: tuple[PartTemplateComponent, ...] = ()


class PartContent(_ContentValue):
    """Only structure this part carried; plain text uses content=None."""

    buttons: tuple[PartButton, ...] | None = None
    quick_replies: tuple[PartQuickReply, ...] | None = None
    elements: tuple[PartElement, ...] | None = None
    media: PartMedia | None = None
    header: PartHeader | None = None
    footer: str | None = None
    sections: tuple[PartSection, ...] | None = None
    button_text: str | None = None
    contacts: tuple[ContactCard, ...] | None = None
    location: PartLocation | None = None
    template: PartTemplate | None = None
    request: Literal["location", "contact"] | None = None
