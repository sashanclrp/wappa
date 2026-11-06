"""Log record formatters: single-line JSON for production, compact names for Rich.

``WappaJSONFormatter`` turns the ``[I:..][U:..]`` context prefix into structured
fields; ``CompactFormatter`` shortens long ``wappa.*`` logger names.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import UTC, datetime

from .context import get_current_request_id

# Parse the current Inbox prefix and the historical T prefix during log-parser
# migration. New Wappa records always emit I, never tenant terminology.
_CTX_PREFIX_RE = re.compile(
    r"^(?:\[(?:I|T):(?P<inbox>[^\]]*)\])?(?:\[U:(?P<user>[^\]]*)\])?\s*(?P<rest>.*)",
    re.DOTALL,
)


class WappaJSONFormatter(logging.Formatter):
    """
    Single-line JSON formatter for production log aggregation.

    Each log record is emitted as one JSON object. Exception tracebacks are
    serialised into the ``exc`` field with newlines escaped, preserving the
    single-line contract required by platforms like Railway.

    Fields emitted per record:
    - ``ts``     – ISO-8601 timestamp (UTC, second precision)
    - ``level``  – log level name
    - ``logger`` – logger name
    - ``msg``    – message text (context prefix stripped)
    - ``inbox`` – inbox ID when present in the message prefix
    - ``user``   – user ID when present in the message prefix
    - ``request_id`` – correlation ID when an HTTP request scope is active
    - ``exc``    – single-line traceback string (only when exception info is present)
    """

    def format(self, record: logging.LogRecord) -> str:
        # Parse context prefix out of the message so it becomes structured fields
        raw_msg = record.getMessage()
        m = _CTX_PREFIX_RE.match(raw_msg)
        inbox = m.group("inbox") if m else None
        user = m.group("user") if m else None
        clean_msg = m.group("rest") if m else raw_msg

        obj: dict[str, str] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": clean_msg,
        }
        if inbox:
            obj["inbox"] = inbox
        if user:
            obj["user"] = user

        request_id = get_current_request_id()
        if request_id:
            obj["request_id"] = request_id

        if record.exc_info:
            obj["exc"] = "".join(traceback.format_exception(*record.exc_info)).replace(
                "\n", "\\n"
            )
            record.exc_info = None  # prevent the base class from appending it again
        elif record.exc_text:
            obj["exc"] = record.exc_text.replace("\n", "\\n")
            record.exc_text = None

        return json.dumps(obj, ensure_ascii=False)


class CompactFormatter(logging.Formatter):
    """Custom formatter that shortens long module names for better readability."""

    def format(self, record: logging.LogRecord) -> str:
        # Shorten long module names for better readability
        if record.name.startswith("wappa."):
            # Convert wappa.core.events.event_dispatcher -> events.dispatcher
            parts = record.name.split(".")
            if len(parts) > 2:
                # Keep last 2 parts for most modules
                if "event_dispatcher" in record.name:
                    record.name = "events.dispatcher"
                elif "default_handlers" in record.name:
                    record.name = "events.handlers"
                elif "whatsapp" in record.name:
                    # For WhatsApp modules, keep whatsapp.component
                    relevant_parts = [
                        p
                        for p in parts
                        if p in ["whatsapp", "messenger", "handlers", "client"]
                    ]
                    record.name = (
                        ".".join(relevant_parts[-2:])
                        if len(relevant_parts) >= 2
                        else ".".join(relevant_parts)
                    )
                else:
                    # Default: keep last 2 parts
                    record.name = ".".join(parts[-2:])

        return super().format(record)
