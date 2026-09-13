"""SSE routes for streaming Wappa events to frontends."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Mapping

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse

from wappa.core.sse import SUPPORTED_SSE_EVENT_TYPES, SSEHub

router = APIRouter(
    prefix="/api/sse",
    tags=["SSE"],
    responses={
        400: {"description": "Invalid SSE request parameters"},
        503: {"description": "SSE plugin not active"},
    },
)


def _parse_event_filters(event_types: str | None) -> set[str] | None:
    """Parse comma-separated event filters and validate allowed values."""
    if event_types is None or not event_types.strip():
        return None

    selected = {item.strip() for item in event_types.split(",") if item.strip()}
    unknown = selected - SUPPORTED_SSE_EVENT_TYPES
    if unknown:
        supported = ", ".join(sorted(SUPPORTED_SSE_EVENT_TYPES))
        invalid = ", ".join(sorted(unknown))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported event types: {invalid}. Supported: {supported}",
        )

    return selected


def _get_event_hub(request: Request) -> SSEHub:
    """Read SSE hub from app state or return 503 when plugin is disabled."""
    event_hub = getattr(request.app.state, "sse_event_hub", None)
    if not isinstance(event_hub, SSEHub):
        raise HTTPException(
            status_code=503,
            detail="SSE plugin is not active. Add SSEEventsPlugin to your Wappa app.",
        )

    return event_hub


def _format_sse_event(
    *,
    event_name: str,
    data: str,
    event_id: str | None = None,
) -> str:
    """Format one SSE message according to the text/event-stream protocol."""
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")

    lines.append(f"event: {event_name}")
    data_lines = data.splitlines() if data else [""]
    lines.extend(f"data: {line}" for line in data_lines)
    return "\n".join(lines) + "\n\n"


@router.get(
    "/events",
    summary="Stream Wappa events via SSE",
    description=(
        "Subscribe to real-time Wappa events. An Inbox filter is qualified by "
        "Platform; optionally filter by user and event types."
    ),
)
async def stream_events(
    request: Request,
    platform: str | None = Query(
        default=None,
        description="Platform for an Inbox filter; required when inbox_id is set.",
    ),
    inbox_id: str | None = Query(
        default=None,
        description="Optional inbox filter (only events for this inbox).",
    ),
    user_id: str | None = Query(
        default=None,
        description="Optional user filter (only events for this user).",
    ),
    event_types: str | None = Query(
        default=None,
        description=(
            "Optional comma-separated event type filters. "
            "Example: incoming_message,outgoing_api_message"
        ),
    ),
) -> EventSourceResponse:
    """Create SSE stream for clients and emit full event envelopes."""
    event_hub = _get_event_hub(request)
    if inbox_id is not None and platform is None:
        raise HTTPException(
            status_code=400,
            detail="platform is required when filtering SSE by inbox_id",
        )
    selected_events = _parse_event_filters(event_types)
    subscription = await event_hub.subscribe(
        platform=platform,
        inbox_id=inbox_id,
        user_id=user_id,
        event_types=selected_events,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(
                        subscription.queue.get(),
                        timeout=20.0,
                    )
                except TimeoutError:
                    yield _format_sse_event(event_name="ping", data="{}")
                    continue

                # Close controls are intentionally not normal SSE envelopes.
                # A queue item without the envelope mapping shape requests a
                # reconnect so clients never continue after a delivery gap.
                if not isinstance(event, Mapping):
                    break

                event_id = event.get("event_id")
                formatted_event_id = event_id if isinstance(event_id, str) else None

                yield _format_sse_event(
                    event_id=formatted_event_id,
                    event_name=str(event.get("event_type", "message")),
                    data=json.dumps(event, ensure_ascii=False),
                )
        finally:
            await event_hub.unsubscribe(subscription.subscriber_id)

    return EventSourceResponse(event_generator())


@router.get(
    "/status",
    summary="SSE status",
    description="Check active SSE subscribers and supported event filters.",
)
async def sse_status(request: Request) -> dict[str, object]:
    """Return SSE plugin runtime status."""
    event_hub = _get_event_hub(request)
    return {
        "status": "active",
        "supported_event_types": sorted(SUPPORTED_SSE_EVENT_TYPES),
        "hub": event_hub.snapshot_metrics().to_dict(),
    }


@router.post(
    "/debug/publish",
    summary="[DEBUG] Publish a test SSE event",
    include_in_schema=False,
)
async def debug_publish_event(request: Request) -> dict[str, str]:
    """Publish a fake SSE event for debugging."""
    from wappa.core.sse.context import sse_event_scope

    body = await request.json()
    event_type = body.get("event_type", "agent_run_completed")
    payload = body.get("payload", {})
    inbox_id = body.get("inbox_id", "")
    user_id = body.get("user_id", "")

    async with sse_event_scope(
        inbox_id=inbox_id,
        user_id=user_id,
        bsuid=user_id,
        phone_number=body.get("phone_number", ""),
        platform="whatsapp",
    ):
        event_hub = _get_event_hub(request)
        result = await event_hub.publish(
            event_type=event_type,
            source="debug",
            payload=payload,
        )
    return {"delivered": str(result.delivered), "event_type": event_type}
