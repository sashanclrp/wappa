"""Splitting one WhatsApp HTTP surface into outbound and service halves.

An embedding Host Application owns its own authenticated send boundary, so it
needs Wappa's raw outbound mutation routes gone — but not the read, upload, and
lookup routes that happen to share the same URL prefix. Modules that mix both
build two routers here instead of listing paths somewhere else, so the line
stays visible right where the routes are declared.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import APIRouter


def outbound_and_service_routers(
    *,
    prefix: str,
    tags: list[str | Enum],
    responses: dict[int | str, dict[str, Any]],
) -> tuple[APIRouter, APIRouter]:
    """Return ``(outbound, service)`` routers sharing one prefix and tags.

    ``outbound`` carries the mutations that send something to a User;
    ``service`` carries everything a host still needs when it owns sending
    itself — uploads, downloads, lookups, limits, and validation.
    """
    return (
        APIRouter(prefix=prefix, tags=tags, responses=responses),
        APIRouter(prefix=prefix, tags=tags, responses=responses),
    )
