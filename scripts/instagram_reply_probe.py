"""Manual, credential-safe Graph probe that bypasses Wappa's quote suppression.

Default: read and compare message IDs only. --send explicitly sends one test
message to the supplied recipient. No retries and no automatic ID conversion.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv


class ProbeError(Exception):
    def __init__(self, summary: dict[str, Any]):
        self.summary = summary


def fingerprint(value: str) -> dict[str, Any]:
    return {
        "length": len(value),
        "sha256_prefix": hashlib.sha256(value.encode()).hexdigest()[:12],
    }


async def request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
    response = await client.request(method, path, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    error = body.get("error") or {}
    if response.is_error or error:
        fields = error if isinstance(error, dict) else {}
        raise ProbeError(
            {
                "http_status": response.status_code,
                "code": fields.get("code"),
                "subcode": fields.get("error_subcode"),
            }
        )
    return body


def history_rows(body: dict) -> list[dict]:
    rows = body.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ProbeError({"reason": "malformed_history; no send attempted"})
    return rows


async def probe(
    client: httpx.AsyncClient,
    *,
    node: str,
    recipient: str,
    webhook_mid: str,
    send: str | None = None,
    expected_fingerprint: str | None = None,
) -> dict:
    if not all(value.strip() for value in (node, recipient, webhook_mid)):
        raise ProbeError({"reason": "blank_identifier; no request attempted"})
    candidates = {"webhook": webhook_mid}
    report: dict[str, Any] = {
        "webhook": fingerprint(webhook_mid),
        "history": [],
        "sent": False,
    }
    if send is None or send.startswith("history:"):
        conversations = await request(
            client,
            "GET",
            f"{quote(node, safe='')}/conversations",
            params={"platform": "instagram", "user_id": recipient},
        )
        rows = history_rows(conversations)
        if len(rows) > 1:
            raise ProbeError({"reason": "ambiguous_conversation; no send attempted"})
        if rows:
            if not isinstance(rows[0].get("id"), str) or not rows[0]["id"]:
                raise ProbeError({"reason": "malformed_history; no send attempted"})
            page = await request(
                client,
                "GET",
                f"{quote(rows[0]['id'], safe='')}/messages",
                params={"fields": "id,created_time,from,to", "limit": 20},
            )
            for index, message in enumerate(history_rows(page)):
                mid = message.get("id")
                if not isinstance(mid, str) or not mid:
                    continue
                label = f"history:{index}"
                candidates[label] = mid
                source = message.get("from") or {}
                if not isinstance(source, dict):
                    raise ProbeError({"reason": "malformed_history; no send attempted"})
                sender = source.get("id")
                if sender == recipient:
                    direction = "inbound"
                elif sender == node:
                    direction = "outbound"
                else:
                    direction = "unknown"
                report["history"].append(
                    {
                        "candidate": label,
                        **fingerprint(mid),
                        "same_as_webhook": mid == webhook_mid,
                        "direction": direction,
                        "created_time": message.get("created_time"),
                    }
                )
    if send is not None:
        if send != "plain" and send not in candidates:
            raise ProbeError({"reason": "candidate_unavailable; no send attempted"})
        if (
            expected_fingerprint
            and send != "plain"
            and fingerprint(candidates[send])["sha256_prefix"] != expected_fingerprint
        ):
            raise ProbeError({"reason": "candidate_changed; no send attempted"})
        payload = {
            "recipient": {"id": recipient},
            "message": {"text": f"Wappa quote probe ({send})"},
        }
        if send != "plain":
            payload["reply_to"] = {"mid": candidates[send]}
        result = await request(
            client, "POST", f"{quote(node, safe='')}/messages", json=payload
        )
        mid = result.get("message_id")
        report.update(
            sent=True,
            candidate=send,
            provider_accepted=isinstance(mid, str) and bool(mid),
            outbound=fingerprint(mid) if isinstance(mid, str) else None,
            quote_rendering="check recipient app; acceptance alone does not prove a quote",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recipient-id",
        required=True,
        help="IGSID from the same Inbox's webhook; never printed",
    )
    parser.add_argument(
        "--webhook-mid",
        required=True,
        help="Exact inbound message.mid; never converted or printed",
    )
    parser.add_argument(
        "--login", choices=("instagram", "facebook"), default="instagram"
    )
    parser.add_argument(
        "--account-id", help="Instagram account ID; defaults to IG_ACCOUNT_ID"
    )
    parser.add_argument(
        "--page-id", help="Required for the Facebook Login/Page-token endpoint"
    )
    parser.add_argument(
        "--token-env",
        default="IG_ACCESS_TOKEN",
        help="Environment key containing the matching access token",
    )
    parser.add_argument("--api-version", default="v25.0")
    parser.add_argument(
        "--send",
        help="Explicitly send ONE test: plain, webhook, or history:N. Default: read-only.",
    )
    parser.add_argument(
        "--expect-fingerprint",
        help="Required for history:N sends: fingerprint from the read-only comparison.",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"v\d+\.\d+", args.api_version):
        parser.error("API version must look like v25.0")
    if args.send is not None and not re.fullmatch(
        r"plain|webhook|history:\d+", args.send
    ):
        parser.error("Choose plain, webhook, or history:N")
    if args.send and args.send.startswith("history:") and not args.expect_fingerprint:
        parser.error(
            "history:N sends require --expect-fingerprint from a read-only comparison"
        )
    if args.expect_fingerprint and not re.fullmatch(
        r"[0-9a-f]{12}", args.expect_fingerprint
    ):
        parser.error("Expected fingerprint must be 12 lowercase hexadecimal characters")
    load_dotenv(".env")
    token = os.getenv(args.token_env)
    node = (
        args.page_id
        if args.login == "facebook"
        else args.account_id or os.getenv("IG_ACCOUNT_ID")
    )
    if not node or not token:
        parser.error(
            "Configure the matching account/page and token environment key first"
        )
    host = "graph.instagram.com" if args.login == "instagram" else "graph.facebook.com"

    async def run():
        async with httpx.AsyncClient(
            base_url=f"https://{host}/{args.api_version}/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        ) as client:
            return await probe(
                client,
                node=node,
                recipient=args.recipient_id,
                webhook_mid=args.webhook_mid,
                send=args.send,
                expected_fingerprint=args.expect_fingerprint,
            )

    try:
        report = asyncio.run(run())
    except ProbeError as exc:
        print(json.dumps({"failed": True, **exc.summary}))
        return 1
    except httpx.HTTPError as exc:
        print(
            json.dumps(
                {"failed": True, "transport_error": type(exc).__name__, "retry": False}
            )
        )
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
