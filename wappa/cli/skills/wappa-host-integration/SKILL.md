---
name: wappa-host-integration
description: Integrates Wappa into a larger Host Application — many WhatsApp and Instagram Inboxes behind one webhook (explicit routing, IInboxDirectorySource, InboxCredentialService, refresh_inbox, X-Wappa-Inbox-ID), sending outside a dispatch with OutboundRuntime, plugins (Auth, CORS, RateLimit, custom and Messenger middleware, SSE events), External Webhook Sources, crons and the HTTP API lane, and upgrading a Host across Wappa's breaking releases. Use when embedding Wappa in a SaaS or multi-tenant backend, adding accounts at runtime, protecting or rate-limiting routes, streaming events to a frontend, receiving third-party webhooks (Stripe, a CRM), scheduling work, or moving to a new Wappa version. Not for single-handler message logic (wappa-apps) or cache and database design (wappa-state-and-storage).
---

# Integrating Wappa into a Host

Wappa owns Platform intake, callback authentication, credential encryption, the Inbox Directory cache, Messenger construction and its HTTP surfaces. The Host owns durable Inbox data, operator authentication and authorization, business transactions, cross-replica delivery and reconciliation. Never move a business concept into Wappa, and never reach into `wappa.core.*` internals: use the public imports named here and in the installed `docs/public-contract.md`.

## Workflow

```
Progress:
- [ ] 1. Inspect: Wappa version, routing mode, plugins already added, Host framework
- [ ] 2. Route: load only the reference for the task
- [ ] 3. Build with public imports; Host transaction first, then tell Wappa
- [ ] 4. Verify: tests for the seam, then one live check; report what wasn't proven
```

**1. Inspect.** `uv run python -c "import wappa; print(wappa.__version__)"`, then read `main.py` for `Wappa(...)` arguments and `add_plugin` calls. When upgrading, read the installed `CHANGELOG.md` before touching code.

**2. Route.**

| Task | Load |
| --- | --- |
| Several Inboxes or Platforms, adding or rotating accounts at runtime, the Directory Source, callbacks, `X-Wappa-Inbox-ID`, sends from jobs (`OutboundRuntime`), credential access for other services | `references/multi-inbox.md` |
| Plugins and middleware: Auth, CORS, RateLimit, custom HTTP middleware, Messenger middleware (window guards, auditing), SSE to a frontend, startup order | `references/plugins.md` |
| Third-party webhooks, crons, the HTTP API lane (`process_api_message`) | `references/runtime-lanes.md` |
| Moving to a new Wappa version | `references/upgrading.md` |
| Per-User timers, Redis, Postgres | `wappa-state-and-storage` skill |
| Connecting customer accounts (Embedded Signup, Unified Login) | `wappa-apps` skill (its connecting-accounts reference) |

**3. Build.** Rules that hold everywhere:

- **Identity is `InboxRef(platform, inbox_id)`.** A bare ID is never enough; the same number can exist on two Platforms. A WhatsApp Inbox is a phone number ID and its account is the WABA (`PlatformAccountRef`).
- **Commit first, then tell Wappa.** Persist the record in the Host's transaction, then call `app.state.inbox_runtime.directory.refresh_inbox(inbox_ref)` (or `deactivate_inbox`). Wappa never writes your tables.
- **Selecting is not authorizing.** `X-Wappa-Inbox-ID` picks the Inbox for an HTTP call; the Host authenticates and authorizes the caller first (`AuthPlugin` or its own).
- **At least once.** Account-wide events fan out to every active Inbox and Meta retries, so make side effects idempotent with the Platform's IDs.
- **Lanes without an Inbox.** `self.messenger`, `self.whatsapp`, `self.instagram` and `self.cache_factory` are `None` in `process_api_message`, system crons and external events no resolver bound. Check before sending; `self.db` is always available.
- **Credentials are never data.** No tokens in caches, logs, AI tools or browsers; resolve per operation with `InboxCredentialAccess`.

**4. Verify.** Test each seam you built: a Directory Source with two Inboxes on two Platforms, a refresh after rotation, a 401 for a bad signature, a 400 for an unknown Inbox, an external event with and without a resolved Inbox. Then run one live round trip. Correct at most three times against specific failing evidence, and report what stays unproven.
