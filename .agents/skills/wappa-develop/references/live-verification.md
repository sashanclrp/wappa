---
checked_on: 2026-11-06
checked_against: Gate A live runs of 2026-11-05 and 2026-11-06 (format matrix, rate-limit governor) and Meta's Instagram and WhatsApp rate-limit pages (Graph v26.0)
revision: 1
---

# Live verification and debugging

## Contents

- Roles
- Read-only tools
- Running a live gate
- Rate limits during live runs
- From evidence to a rule

## Roles

The user runs the server and every live send; the agent prepares the build, reads the evidence and records it. Never start a server on the user's port (`logs/dev.pid` names the running one and its port), never send to a real account, and never print a token. Wappa code edits don't reload the lab app: ask the user to restart it after each change. The lab is `instagram_conversations_example` in the sibling `wappa_examples` repository (WhatsApp and Instagram, the form-intake Score, `/formats` for the media matrix, `/connect/*` routes).

## Read-only tools

Use these before reading logs, Meta state or Redis by hand:

| Tool | Answers |
| --- | --- |
| `scripts/devlog.sh [--dir APP] [--since HH:MM] [--restart] [PATTERN]` | What the server logged, from `logs/current.log` (read, never edit) |
| `uv run python <wappa>/scripts/meta_inspect.py app-subscriptions` / `token ENV_NAME` / `ig-subscribed-apps --inbox ID` | App webhook fields and callback, token type, scopes and expiry, account subscriptions; run from the app folder |
| `uv run python <wappa>/scripts/redis_inspect.py --platform P --inbox ID [--user U] [--values]` | One Inbox's keys across Redis databases 0–4, secrets redacted |
| `scripts/env_keys.sh [.env]` | Which keys are set, never their values |
| `uv run python scripts/promote_payload.py SRC [--name N]` | A captured payload (`SYSTEM_CAPTURE_PAYLOADS=1`) into `tests/fixtures/meta_payloads/`, refusing secrets |
| `uv run python scripts/verify_redis_cache_live.py` | Every cache against a real Redis |

## Running a live gate

1. Write the cases first (case ID, steps, expected evidence) in the PRD's live test plan, for Instagram `docs/backlog/in_progress/261103-instagram-conversations/tests/live-test-plan.md`.
2. Make sure the build under test is what the user runs: commit or note the diff, ask for a restart, then check the startup banner in `devlog.sh --restart`.
3. The user sends; you read the log and Meta state. Record four separate facts per case: the callback 200, Meta's acceptance (a `message_id`), the status webhook, and what the User saw (the user reports it, with screenshots when rendering matters).
4. Log each result with time and build in the plan's results log, including failures and "not run".

## Rate limits during live runs

Instagram's code `4` is an app-level budget (about 200 calls per hour per daily user, over a rolling hour). Wappa's governor blocks the whole app for 300 s on code 4, doubling on repeats, and usage warnings fire at 80%. Run matrices in slices of about five calls, 10–15 minutes apart; a retry storm only extends the block. WhatsApp allows about 1 message every 6 s per recipient. A `rate_limited` result in the lab is not a format rejection: label it as such.

## From evidence to a rule

A media or behavior rule changes only from recorded evidence:

1. The live result is in the plan (link or upload, format, codec, what rendered).
2. Encode the rule before I/O in the Platform's rules module (`wappa/messaging/whatsapp/media/rules.py` and `wappa/domain/media_probe.py`, or `wappa/messaging/instagram/media/rules.py`), with an error that names the problem and says to convert first. Never add conversion.
3. Add tests for the refusal and the accepted neighbor (`tests/test_whatsapp_media_rules.py`, `tests/test_instagram_media_emulation.py`, `tests/test_one_method_per_action.py`).
4. Update the PRD's media-formats reference (`docs/backlog/in_progress/261103-instagram-conversations/references/media-formats.md`), the shipped copy `wappa/cli/skills/wappa-apps/references/media-formats.md` (keep the unified kit valid), `messaging.md` rows, `docs/public-contract.md`, and `CHANGELOG.md` (a new refusal is a break).
