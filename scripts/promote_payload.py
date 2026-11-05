#!/usr/bin/env python3
"""Promote a captured Meta webhook payload into a schema-drift test fixture.

Usage:
    uv run python scripts/promote_payload.py SRC [--name NAME] [--force]

SRC is a file written by payload capture (``SYSTEM_CAPTURE_PAYLOADS=1``):
``<app>/logs/payloads/<platform>/<kind>-<timestamp>.json``. The copy lands in
``tests/fixtures/meta_payloads/<platform>/<NAME>.json`` and is replayed by
``tests/test_meta_payload_fixtures.py`` in strict schema mode.

The payload is checked for anything secret-looking (tokens, secret-named
keys, signatures, ``access_token=`` URLs) and the script refuses (exit 1) if
it finds any, printing JSON paths only. Message text is masked as capture
does. Phone numbers and IDs are kept: replace real ones with obviously fake
values of the same shape before committing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from wappa.core.inbound.payload_capture import find_secrets, redact_payload

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "meta_payloads"
PLATFORMS = {"whatsapp_business_account": "whatsapp", "instagram": "instagram"}


def _platform(src: Path, payload: dict) -> str:
    by_object = PLATFORMS.get(str(payload.get("object")))
    if by_object:
        return by_object
    if src.parent.name in PLATFORMS.values():
        return src.parent.name
    raise SystemExit(
        f"cannot tell the platform of {src} (object={payload.get('object')!r})"
    )


def _default_name(src: Path) -> str:
    # "<kind>-20261105T120001002345Z" -> "<kind>"
    return re.sub(r"-\d{8}T\d{6}\d*Z$", "", src.stem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("src", type=Path, help="captured payload JSON")
    parser.add_argument(
        "--name", help="fixture name without .json (default: capture kind)"
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing fixture"
    )
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"refused: cannot read JSON from {args.src}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("refused: payload root must be a JSON object", file=sys.stderr)
        return 1

    hits = find_secrets(payload)
    if hits:
        print("refused: secret-looking values at:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1

    cleaned = redact_payload(payload)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", args.name or _default_name(args.src))
    dest = FIXTURES / _platform(args.src, payload) / f"{name}.json"
    if dest.exists() and not args.force:
        print(
            f"refused: {dest.relative_to(REPO)} exists (use --name or --force)",
            file=sys.stderr,
        )
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"promoted -> {dest.relative_to(REPO)}")
    print("next: replace real phone numbers/IDs with fake same-shape values, then")
    print("      uv run pytest tests/test_meta_payload_fixtures.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
