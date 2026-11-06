"""User profile read: Graph lookup by IGSID merged over the webhook evidence."""

from __future__ import annotations

from wappa.domain.user_profile import PlatformUserProfile
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

from ..errors import read_failure
from ._base import _InstagramBase

PROFILE_FIELDS = "name,username,profile_pic"


class _ProfileMixin(_InstagramBase):
    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        """Graph profile lookup by IGSID, merged over the webhook evidence.

        Never raises for Platform failures: a refused or unknown lookup
        returns the evidence with ``not_found`` / ``access_denied`` /
        ``rejected`` / ``unavailable``.
        """
        if not user.platform_user_id:
            raise ValueError(
                "Instagram profiles resolve from Instagram evidence "
                "(UserBase.platform_user_id)"
            )
        evidence = PlatformUserProfile.from_evidence(self.platform, user)
        response = await self._graph.request(
            "GET",
            user.platform_user_id,
            params={"fields": PROFILE_FIELDS},
            operation="Instagram user profile read",
        )
        if not response.ok:
            return evidence.model_copy(
                update={"outcome": read_failure(response).outcome}
            )
        body = response.body

        def text(key: str) -> str | None:
            value = body.get(key)
            return value if isinstance(value, str) and value.strip() else None

        return evidence.model_copy(
            update={
                "profile_name": text("name") or evidence.profile_name,
                "username": text("username") or evidence.username,
                "picture_url": text("profile_pic"),
                "raw": body,
            }
        )
