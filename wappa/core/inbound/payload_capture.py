"""Opt-in capture of authenticated raw Meta webhook bodies (DEV only).

With ``SYSTEM_CAPTURE_PAYLOADS=1`` outside PROD, the webhook controller hands
each body that passed signature verification to :func:`capture_payload`,
which writes a redacted copy to
``<log_dir>/payloads/<platform>/<kind>-<timestamp>.json``. Captures become
test fixtures (``scripts/promote_payload.py``), so redaction keeps structure,
phone numbers and IDs, masks message text, and removes anything secret.

:func:`find_secrets` is the shared gate: capture and promotion both refuse to
keep a payload it flags.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wappa.core.logging.logger import redact_secrets

REDACTED = "[REDACTED]"
MASKED_TEXT = "[masked text]"

# Keys whose value is a secret wherever they appear.
_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|signature|ciphertext|authorization|api_?key"
    r"|appsecret)",
    re.IGNORECASE,
)
# Meta user/page/app tokens and other long bearer material inside any string.
_TOKEN_VALUE = re.compile(
    r"(?<![A-Za-z0-9])(?:EAA[A-Za-z0-9]{20,}|IG(?:AA|QV|QW)[A-Za-z0-9_\-]{20,})"
)
_SIGNATURE_VALUE = re.compile(r"sha256=[0-9a-fA-F]{64}")
_UNREDACTED_QUERY = re.compile(
    r"(?:access_token|input_token|client_secret|appsecret_proof|fb_exchange_token)"
    r"=(?!\[REDACTED\])[^&\s\"']+"
)
_UNREDACTED_BEARER = re.compile(r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._\-]{20,}")

# (parent key, key) pairs that hold end-user message text.
_TEXT_FIELDS = {
    ("text", "body"),  # WhatsApp text message
    ("message", "text"),  # Instagram DM
    ("value", "text"),  # Instagram comment / Live comment
}
_TEXT_KEYS = {"caption"}


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY.search(key))


def _redact_string(value: str) -> str:
    value = redact_secrets(value)
    value = _TOKEN_VALUE.sub(REDACTED, value)
    return _SIGNATURE_VALUE.sub(f"sha256={REDACTED}", value)


def redact_payload(value: Any, *, parent: str | None = None) -> Any:
    """Return a copy with secrets removed and end-user message text masked."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_secret_key(str(key)) and item not in (None, "", [], {}):
                out[key] = REDACTED
            elif isinstance(item, str) and (
                (parent, key) in _TEXT_FIELDS or key in _TEXT_KEYS
            ):
                out[key] = MASKED_TEXT
            else:
                out[key] = redact_payload(item, parent=str(key))
        return out
    if isinstance(value, list):
        return [redact_payload(item, parent=parent) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _walk(value: Any, path: str = "$") -> Iterator[tuple[str, str | None, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            yield child, str(key), item
            yield from _walk(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield child, None, item
            yield from _walk(item, child)


def find_secrets(value: Any) -> list[str]:
    """JSON paths that still look secret (never the secret itself)."""
    hits: list[str] = []
    for path, key, item in _walk(value):
        if key is not None and _is_secret_key(key):
            if isinstance(item, str) and item not in ("", REDACTED):
                hits.append(f"{path} (secret-named key)")
            continue
        if isinstance(item, str):
            for name, pattern in (
                ("Meta token", _TOKEN_VALUE),
                ("signature", _SIGNATURE_VALUE),
                ("query secret", _UNREDACTED_QUERY),
                ("bearer token", _UNREDACTED_BEARER),
            ):
                if pattern.search(item):
                    hits.append(f"{path} ({name})")
    return hits


def capture_kind(payload: dict[str, Any]) -> str:
    """A filename-safe label: the webhook field, refined by event type."""
    entries = payload.get("entry")
    entry = entries[0] if isinstance(entries, list) and entries else {}
    if not isinstance(entry, dict):
        return "unknown"

    changes = entry.get("changes")
    if isinstance(changes, list) and changes and isinstance(changes[0], dict):
        change = changes[0]
        field = str(change.get("field") or "change")
        value = change.get("value") if isinstance(change.get("value"), dict) else {}
        if field == "messages" and isinstance(value, dict):
            if value.get("statuses"):
                return _safe("statuses")
            messages = value.get("messages")
            if isinstance(messages, list) and messages:
                first = messages[0] if isinstance(messages[0], dict) else {}
                kind = str(first.get("type") or "message")
                interactive = first.get("interactive")
                if kind == "interactive" and isinstance(interactive, dict):
                    kind = f"interactive.{interactive.get('type', 'unknown')}"
                return _safe(f"messages.{kind}")
        return _safe(field)

    messaging = entry.get("messaging")
    if isinstance(messaging, list) and messaging and isinstance(messaging[0], dict):
        event = messaging[0]
        for kind in (
            "message",
            "postback",
            "reaction",
            "read",
            "referral",
            "message_edit",
            "optin",
        ):
            if kind in event:
                message = event[kind]
                if (
                    kind == "message"
                    and isinstance(message, dict)
                    and message.get("is_echo")
                ):
                    return "messaging.echo"
                return _safe(f"messaging.{kind}")
        return "messaging"
    return "unknown"


def _safe(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:80] or "unknown"


def capture_payload(
    payload: dict[str, Any],
    *,
    platform: str,
    log_dir: str | Path,
    now: datetime | None = None,
) -> Path:
    """Write the redacted payload; raise if redaction left a secret behind."""
    redacted = redact_payload(payload)
    leaks = find_secrets(redacted)
    if leaks:
        raise ValueError(
            "payload capture refused: redaction left secret-looking values at "
            + ", ".join(leaks)
        )
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    folder = Path(log_dir) / "payloads" / _safe(platform.lower())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{capture_kind(payload)}-{stamp}.json"
    path.write_text(
        json.dumps(redacted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


__all__ = [
    "MASKED_TEXT",
    "REDACTED",
    "capture_kind",
    "capture_payload",
    "find_secrets",
    "redact_payload",
]
