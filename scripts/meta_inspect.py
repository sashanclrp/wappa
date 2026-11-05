#!/usr/bin/env python3
"""Read-only Meta Graph diagnostics for a Wappa app. Never prints a token.

Usage (run from the app folder so its .env and .local/ are found):
    uv run python ../../wappa/scripts/meta_inspect.py app-subscriptions
    uv run python ../../wappa/scripts/meta_inspect.py token IG_ACCESS_TOKEN
    uv run python ../../wappa/scripts/meta_inspect.py ig-subscribed-apps --inbox 1784...

Subcommands:
    app-subscriptions   GET /{app-id}/subscriptions with the app token
                        (META_APP_ID|META_APP_SECRET): webhook objects, fields,
                        callback URL, active flag.
    token ENV_NAME      GET /debug_token for the token held in env var ENV_NAME:
                        type, app, validity, expiry, scopes, granular scopes.
    ig-subscribed-apps  GET /{ig-id}/subscribed_apps with the Inbox's token,
                        decrypted through Wappa's Inbox Directory and
                        CredentialCodec (SYSTEM_TOKEN_ENC_KEY) from the Host's
                        records file (default .local/inboxes.json).

Credentials come from the process environment, then --env-file (default
./.env). Graph version and base URL come from Wappa settings
(META_API_VERSION, META_BASE_URL). Tokens show as their last 4 characters.
Every call is a GET.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


def mask(value: str | None) -> str:
    if not value:
        return "<unset>"
    return f"…{value[-4:]}" if len(value) > 8 else "…(short)"


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"error: {name} is not set (env or --env-file)")
    return value


def _graph() -> str:
    from wappa.core.config.settings import settings

    return f"{settings.base_url.rstrip('/')}/{settings.api_version}"


def _when(epoch: Any) -> str:
    if not epoch:
        return "never"
    return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat(timespec="seconds")


def _get(path: str, token: str, params: dict[str, str] | None = None) -> Any:
    response = httpx.get(
        f"{_graph()}/{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:300]}
    if not response.is_success:
        error = body.get("error", body) if isinstance(body, dict) else body
        detail = {
            k: error.get(k)
            for k in ("message", "type", "code", "error_subcode")
            if isinstance(error, dict)
        }
        raise SystemExit(f"Meta returned HTTP {response.status_code}: {detail}")
    return body


def _app_token() -> tuple[str, str]:
    app_id = _require("META_APP_ID")
    return app_id, f"{app_id}|{_require('META_APP_SECRET')}"


def cmd_app_subscriptions(_: argparse.Namespace) -> int:
    app_id, app_token = _app_token()
    body = _get(f"{app_id}/subscriptions", app_token)
    print(f"app {app_id} (app token {mask(app_token)}) → {_graph()}")
    data = body.get("data", []) if isinstance(body, dict) else []
    if not data:
        print("  no webhook subscriptions")
    for sub in data:
        print(f"- object={sub.get('object')} active={sub.get('active')}")
        print(f"  callback_url={sub.get('callback_url')}")
        fields = [
            f"{f.get('name')}@{f.get('version')}" if isinstance(f, dict) else str(f)
            for f in sub.get("fields", [])
        ]
        print(f"  fields ({len(fields)}): {', '.join(sorted(fields))}")
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    token = _require(args.env_name)
    _, app_token = _app_token()
    body = _get("debug_token", app_token, params={"input_token": token})
    data = body.get("data", {}) if isinstance(body, dict) else {}
    print(f"{args.env_name} = {mask(token)}")
    for key in ("type", "application", "app_id", "is_valid"):
        print(f"  {key}: {data.get(key)}")
    for key in ("user_id", "profile_id"):
        if data.get(key):
            print(f"  {key}: {data.get(key)}")
    print(f"  expires_at: {_when(data.get('expires_at'))}")
    print(f"  data_access_expires_at: {_when(data.get('data_access_expires_at'))}")
    if data.get("error"):
        print(f"  error: {data['error'].get('message')}")
    print(f"  scopes: {', '.join(data.get('scopes', [])) or '-'}")
    for grant in data.get("granular_scopes", []):
        targets = grant.get("target_ids")
        print(
            f"  granular: {grant.get('scope')}"
            + (f" → {', '.join(targets)}" if targets else " (all)")
        )
    return 0


class _JsonRecordsSource:
    """Read-only IInboxDirectorySource over a Host JSON records file."""

    def __init__(self, path: Path) -> None:
        from wappa.domain.inbox import parse_inbox_credential_record

        raw = json.loads(path.read_text(encoding="utf-8"))
        self._records = {k: parse_inbox_credential_record(v) for k, v in raw.items()}

    async def get_inbox(self, inbox_ref: Any) -> Any:
        return self._records.get(str(inbox_ref))

    async def list_inboxes_for_platform_account(self, account_ref: Any) -> Any:
        return tuple(r for r in self._records.values() if r.account_ref == account_ref)


async def _inbox_token(inbox_id: str, records: Path) -> str:
    from wappa.core.config.settings import settings
    from wappa.core.security.credential_codec import CredentialCodec
    from wappa.domain.inbox import InboxRef
    from wappa.domain.inbox.services import InboxDirectory
    from wappa.persistence.inbox_directory import InboxDirectoryTable
    from wappa.persistence.scope import create_system_table_cache
    from wappa.schemas.core.types import PlatformType

    if not records.exists():
        raise SystemExit(f"error: records file {records} not found (--records)")
    directory = InboxDirectory(
        source=_JsonRecordsSource(records),
        table=InboxDirectoryTable(create_system_table_cache("memory")),
        codec=CredentialCodec.from_environment(
            settings.system_token_enc_key, settings.system_token_enc_previous_keys
        ),
    )
    ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=inbox_id)
    credentials = await directory.resolve_credentials(ref)
    return credentials.access_token.get_secret_value()


def cmd_ig_subscribed_apps(args: argparse.Namespace) -> int:
    token = asyncio.run(_inbox_token(args.inbox, Path(args.records)))
    body = _get(f"{args.inbox}/subscribed_apps", token)
    print(f"instagram Inbox {args.inbox} (token {mask(token)}) → {_graph()}")
    data = body.get("data", []) if isinstance(body, dict) else []
    if not data:
        print("  no apps subscribed: webhooks for this account will not fire")
    for app in data:
        fields = app.get("subscribed_fields", [])
        others = {k: v for k, v in app.items() if k != "subscribed_fields"}
        print(f"- app {others or '(Meta returned no app name/id)'}")
        print(f"  subscribed_fields ({len(fields)}): {', '.join(sorted(fields))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Meta Graph diagnostics for a Wappa app.",
        epilog="Run from the app folder; tokens are masked to the last 4 chars.",
    )
    parser.add_argument("--env-file", default=".env", help="dotenv file (default .env)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "app-subscriptions", help="GET /{app-id}/subscriptions"
    ).set_defaults(func=cmd_app_subscriptions)
    token = sub.add_parser("token", help="GET /debug_token for a token env var")
    token.add_argument("env_name", help="name of the env var holding the token")
    token.set_defaults(func=cmd_token)
    ig = sub.add_parser("ig-subscribed-apps", help="GET /{ig-id}/subscribed_apps")
    ig.add_argument("--inbox", required=True, help="Instagram professional account ID")
    ig.add_argument(
        "--records",
        default=".local/inboxes.json",
        help="Host Inbox records file (default .local/inboxes.json)",
    )
    ig.set_defaults(func=cmd_ig_subscribed_apps)

    args = parser.parse_args(argv)
    load_dotenv(args.env_file, override=False)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
