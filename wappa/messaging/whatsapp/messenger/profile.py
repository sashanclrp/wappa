"""Platform User Profile resolution (``resolve_platform_user_profile``)."""

from __future__ import annotations

from wappa.domain.user_profile import PlatformUserProfile
from wappa.messaging.whatsapp.messenger._base import _WhatsAppMessengerBase
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase


class _ProfileMixin(_WhatsAppMessengerBase):
    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        """The webhook evidence as the profile; Cloud API has no User lookup."""
        if user.platform_user_id is not None:
            raise ValueError(
                "WhatsApp profiles resolve from WhatsApp evidence "
                "(phone number, BSUID), not a native Platform user ID"
            )
        return PlatformUserProfile.from_evidence(PlatformType.WHATSAPP, user)
