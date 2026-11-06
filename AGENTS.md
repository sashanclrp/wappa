# AGENTS.md

Wappa is a Platform-facing messaging runtime library and CLI for WhatsApp and Instagram. It owns webhook intake, message sending, event dispatch, runtime cache scoping, and its public contract; the embedding Host Application owns every business concept.

Before a non-trivial change, read what it touches. Read a large doc by its headings first (`rg -n '^#{1,3} ' FILE`), then only the section you need, one file per command:

- **Language**: `CONTEXT.md` before naming anything. Name things in its terms (Inbox, `InboxRef`, Platform, Host Application); its Anti-Language table lists the words that never enter Wappa, tenancy first. `CONTEXT-MAP.md` locates each context's own glossary.
- **Architecture**: root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` before changing a module, seam, adapter, Messenger method, API route, message type, webhook, or credential path; they hold the callback-authentication, credential-authority, and layering rules, and `wappa/messaging/`, `wappa/api/` and `wappa/webhooks/` each list the file chain one change touches.
- **Decisions**: `docs/adr/` before reversing or extending a recorded decision.
- **Contract**: `docs/public-contract.md` before changing anything a Host can import, call, configure, subscribe to, or scaffold.
- **Code**: `CODING_STANDARDS.md` before writing code or tests, updating docs, or committing.
- **Design**: the `grill-with-docs` skill for a design discussion, domain naming, or an ADR.
- **Changing Wappa**: the `wappa-develop` skill for the change chain of a Messenger method, lane, route, media rule or new Platform, live verification, and keeping the shipped Host skills (`wappa/cli/skills/`) true in the same change.
- **Live debugging**: the read-only tools in `scripts/` before reading logs, Meta state or Redis by hand: `devlog.sh` (the server log through `logs/current.log`, which you only read, never edit), `meta_inspect.py` (app subscriptions and tokens), `redis_inspect.py` (one Inbox's keys), `env_keys.sh` (which `.env` keys are set). `logs/dev.pid` names the running server and its port.
