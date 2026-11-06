"""WhatsApp adapter models: wire responses, media rules, Templates, validators.

The neutral HTTP request models (text, media, interactive, contact, location)
live in ``wappa.schemas.requests``.
"""

from .media_models import MediaType
from .specialized_models import (
    BusinessContact,
    ContactValidationResult,
    LocationValidationResult,
    PersonalContact,
)
from .template_models import (
    TemplateParameter,
    TemplateParameterType,
    TemplateStateConfig,
    WhatsAppTemplateMediaType,
    WhatsAppTemplateType,
)

__all__ = [
    "MediaType",
    "ContactValidationResult",
    "LocationValidationResult",
    "BusinessContact",
    "PersonalContact",
    "TemplateParameter",
    "TemplateParameterType",
    "TemplateStateConfig",
    "WhatsAppTemplateMediaType",
    "WhatsAppTemplateType",
]
