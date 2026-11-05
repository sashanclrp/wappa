# AGENTS.md

Wappa is a Platform-facing messaging runtime library and CLI for WhatsApp and Instagram. It owns webhook intake, message sending, event dispatch, runtime cache scoping, and its public contract; the embedding Host Application owns every business concept.

Before a non-trivial change, read what it touches:

- **Language**: `CONTEXT.md` before naming anything. Name things in its terms (Inbox, `InboxRef`, Platform, Host Application); its Anti-Language table lists the words that never enter Wappa, tenancy first. `CONTEXT-MAP.md` locates each context's own glossary.
- **Architecture**: root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` before changing a module, seam, adapter, webhook, or credential path; they hold the callback-authentication, credential-authority, and layering rules.
- **Decisions**: `docs/adr/` before reversing or extending a recorded decision.
- **Contract**: `docs/public-contract.md` before changing anything a Host can import, call, configure, subscribe to, or scaffold.
- **Code**: `CODING_STANDARDS.md` before writing code or tests, updating docs, or committing.
- **Design**: the `grill-with-docs` skill for a design discussion, domain naming, or an ADR.
