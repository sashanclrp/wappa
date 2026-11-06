"""What a Platform says about one User: ``IMessenger.resolve_platform_user_profile``.

ADR-0025 rule 10. Field names match ``UserBase`` so a Host merges the profile
into its own record field for field. Wappa never persists, caches or merges
it with history; the Host owns that policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.domain.interfaces.conversation_capabilities import ReadOutcome
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces.base_components import UserBase


class PlatformUserProfile(BaseModel):
    """Every fact the Platform provides about a User, from evidence and lookup.

    ``outcome`` is ``found`` when the facts are complete for the Platform:
    evidence-only Platforms (WhatsApp) always report ``found``. A failed
    lookup (Instagram) keeps the webhook evidence and reports why it failed.
    ``raw`` is the Platform's lookup body and never serialises.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: PlatformType
    outcome: ReadOutcome = ReadOutcome.FOUND
    platform_user_id: str | None = None
    bsuid: str | None = None
    parent_bsuid: str | None = None
    phone_number: str | None = None
    username: str | None = None
    country_code: str | None = None
    profile_name: str | None = None
    picture_url: str | None = None
    raw: dict[str, Any] | None = Field(default=None, exclude=True)

    @classmethod
    def from_evidence(
        cls, platform: PlatformType, user: UserBase
    ) -> PlatformUserProfile:
        """The facts the inbound webhook already proved, as a ``found`` profile."""
        return cls(
            platform=platform,
            platform_user_id=user.platform_user_id,
            bsuid=user.bsuid,
            parent_bsuid=user.parent_bsuid,
            phone_number=user.phone_number or None,
            username=user.username,
            country_code=user.country_code,
            profile_name=user.profile_name,
        )

    @property
    def found(self) -> bool:
        return self.outcome is ReadOutcome.FOUND


__all__ = ["PlatformUserProfile"]
