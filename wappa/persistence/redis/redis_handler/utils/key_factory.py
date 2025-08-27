from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger("RedisKeyFactory")


class KeyFactory(BaseModel):
    """Pure stateless helpers for Wappa cache key generation."""

    user_prefix: str = Field(default="user")
    handler_prefix: str = Field(default="state")
    table_prefix: str = Field(default="df")
    pk_marker: str = Field(default="pkid")

    # ---- builders ---------------------------------------------------------
    def user(self, tenant: str, user_id: str) -> str:
        return f"{tenant}:{self.user_prefix}:{user_id}"

    def handler(self, tenant: str, name: str, user_id: str) -> str:
        return f"{tenant}:{self.handler_prefix}:{name}:{user_id}"

    def table(self, tenant: str, table: str, pkid: str) -> str:
        safe_tbl = table.replace(":", "_")
        safe_pk = pkid.replace(":", "_")
        return f"{tenant}:{self.table_prefix}:{safe_tbl}:{self.pk_marker}:{safe_pk}"


# Default instance for global use
default_key_factory = KeyFactory()
