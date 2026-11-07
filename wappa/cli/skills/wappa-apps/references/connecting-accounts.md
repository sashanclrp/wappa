---
checked_on: 2026-11-06
checked_against: Meta Instagram API with Unified Login and WhatsApp Embedded Signup pages (Graph v26.0), wappa/connections/ (whatsapp.py, instagram.py, contract.py) and Wappa's tests/test_instagram_connection.py
revision: 4
---

# Connecting accounts: one flow for WhatsApp and Instagram

## Contents

- One flow, every Platform
- What differs per Platform
- Activate, persist, refresh, revoke
- Trusted credential access
- Host-initiated sends
- Extension webhook fields

## One flow, every Platform

Connecting an account is one contract, `IInboxConnector` (ADR-0026). `WhatsAppConnector` (Embedded Signup) and `InstagramConnector` (Unified Login) both implement it on the same Meta Business Login core, with the same methods and errors. Write one set of Host routes, keyed by Platform, and both work. The Host owns the routes, the authenticated operator, intent storage, the Owner/Channel mapping and transactions.

```python
from wappa.connections import (
    ConnectionCancelledError, ConnectionProviderError, ConnectionStateError,
    InstagramConnector, MetaLoginConfig, WhatsAppConnector,
)

def login(config_id: str, redirect_uri: str | None) -> MetaLoginConfig:
    return MetaLoginConfig(app_id=META_APP_ID, app_secret=META_APP_SECRET,
                           config_id=config_id, redirect_uri=redirect_uri)

CONNECTORS = {   # one Meta app; one login configuration per Platform
    "whatsapp": WhatsAppConnector(login(WA_CONFIG_ID, None), client_provider=lambda: http,
                                  intent_store=host_intent_store),
    "instagram": InstagramConnector(login(IG_CONFIG_ID, f"{BASE}/connect/instagram/callback"),
                                    client_provider=lambda: http, intent_store=host_intent_store),
}

auth = await CONNECTORS[platform].begin(host_subject=operator_session_id)   # auth.url, auth.state
grant = await CONNECTORS[platform].complete(state=state, host_subject=operator_session_id,
                                            code=code, error=error, error_reason=error_reason)
for inbox in grant.inboxes:          # DiscoveredInbox: inbox_ref, account_ref, display_name, readiness
    if inbox.readiness.conversation_ready:
        ...                          # offer it to the operator, then activate (below)
```

`complete` consumes the one-use state before exchanging the code, so a replay, an expired attempt or a different operator raises `ConnectionStateError`. A cancelled dialog raises `ConnectionCancelledError`, and a provider refusal raises `ConnectionProviderError(code)`. `intent_store` is your `IConnectionIntentStore` (atomic, one-use `consume()`); `InMemoryConnectionIntentStore` is for single-process examples only. Missing optional scopes never block messaging: `readiness.missing_required_scopes` lists what does.

## What differs per Platform

Only configuration differs; your code stays the same.

| | WhatsApp (Embedded Signup) | Instagram (Unified Login) |
| --- | --- | --- |
| Meta login configuration | a WhatsApp Embedded Signup `config_id` | an Instagram-compatible Facebook Login for Business `config_id` |
| Dialog | usually the JavaScript SDK popup: pass its `code` to `complete` and set `redirect_uri=None`; Wappa adds `extras={"sessionInfoVersion": "3"}` | a redirect to `auth.url`; register `redirect_uri` in the app (it is not the webhook URL) |
| Required scopes | `whatsapp_business_management`, `whatsapp_business_messaging` | `instagram_basic`, `instagram_manage_messages`; `instagram_manage_comments` enables comments |
| What becomes an Inbox | each phone number of each shared WABA (`inbox_id` = `phone_number_id`; account = the WABA) | each account in `/me/assigned_instagram_accounts` (`/me` is the system user, never an Inbox) |
| `activate` subscribes | the app to the **WABA** (`POST /{waba}/subscribed_apps`) | the account's webhook fields (`activated.details` has the outcome per field; `message_edit` is not offered) |
| `disconnect` stops | every number in that WABA, so call it only when no other active Inbox shares the WABA | that account |
| Revocation signal | `process_inbox_connection` (`account_offboarded`, `account_reconnected`) | none: Unified Login sends no deauthorize; revoke from your side |
| Token | Business Integration System User token, persisted encrypted | business-owned `SYSTEM_USER` token that never expires |

Embedded Signup coexistence numbers are already registered, so Wappa calls no `/register` (two-step PIN). For a WhatsApp Inbox you configure by hand (no Embedded Signup), see `meta-app-setup.md`.

## Activate, persist, refresh, revoke

Here `app` is the FastAPI app: `request.app` in a route, or `wappa.asgi` for the `Wappa` object.

```python
runtime = app.state.inbox_runtime
activated = await connector.activate(grant, inbox.inbox_ref,
                                     credentials=runtime.credential_service,
                                     previous=existing_record)  # rotates when present
host_store.put(activated.record)                              # 1. Host commit
await runtime.directory.refresh_inbox(inbox.inbox_ref)        # 2. then refresh Wappa
# activated.webhooks_subscribed, activated.details (per-field outcomes)
```

Refuse to silently reactivate an inactive (revoked) record. On Instagram, Wappa mounts no deauthorize route: that callback fires only for Instagram Login grants, which Unified Login never creates. A Host data-deletion callback posts a `signed_request`; verify it with `parse_signed_request(value, app_secret)`. To revoke: first resolve the token (`credential = await InboxCredentialAccess.from_app(app).resolve(inbox_ref)`, below), call `connector.disconnect(record.inbox_ref, record.account_ref, credential.access_token)` to stop webhooks (on WhatsApp only when no other active Inbox shares the WABA), then commit `credential_service.create_inactive_record(record)` and call `await runtime.directory.deactivate_inbox(inbox_ref)`. After rotation or deactivation, the next resolution sees the change; in-flight calls are not cancelled.

Revoke an Instagram Inbox through the business portfolio's system user or your connector: deactivate the record, then `connector.disconnect`. On WhatsApp, also deactivate the record when `process_inbox_connection` reports `account_offboarded`.

## Recovering a reconnected WhatsApp account

`account_reconnected` reaches `process_inbox_connection` even when every Inbox of that WABA is inactive, once Wappa has checked the signature and that the Inbox belongs to the account. On an inactive Inbox there is no token in play: `self.messenger` and `self.whatsapp` are `None`, while `self.cache_factory` and `self.db` work. You decide whether to restore it:

```python
async def process_inbox_connection(self, webhook):
    if webhook.state is not InboxConnectionState.RECONNECTED:
        return
    host_store.put(active_record)                                    # 1. Host commit
    await app.state.inbox_runtime.directory.refresh_inbox(self.inbox_ref)  # 2. then refresh
    async with self.scope() as ready:                                # 3. only to send now
        ...
```

An account-only event fans out once per known Inbox, and Meta can repeat it, so make this idempotent. An already restored Inbox receives it with a Messenger. Ordinary messages and `account_offboarded` to an inactive Inbox stay refused with 400. If your handler fails after Wappa accepted the callback, nothing retries it, so keep a Host recovery path. Only this event is routed this way, and its live payload has not been captured yet: log the first real one.

## Trusted credential access

For extension clients Wappa does not cover (publishing, insights):

```python
from wappa.domain.inbox import InboxCredentialAccess

credential = await InboxCredentialAccess.from_app(app).resolve(inbox_ref)
headers = credential.authorization_header()
```

Authorize the caller first; knowing an Inbox ID grants nothing. Resolve the credential for each operation and never cache it. Keep it out of AI tool arguments, browsers, logs and durable plaintext. Never import Wappa's internal resolver or decrypt records yourself.

## Host-initiated sends

For agent replies, delayed jobs and human takeover, use `messenger = await OutboundRuntime.from_app(app).messenger(inbox_ref)`. Apply your own takeover and pause check right before each send, including sends from jobs scheduled before the takeover.

## Extension webhook fields

```python
app.register_webhook_field("story_insights", parser=StoryInsight, handler=on_insight,
                           platform=PlatformType.INSTAGRAM)
```

Built-in Instagram fields are reserved. The parser must be pure. A parse failure rejects the whole signed batch before anything is scheduled. An unknown field that is not registered becomes `SystemWebhook(UNSUPPORTED_EVENT)`. Registering a field does not grant permissions or subscribe the account, so add the field to your subscription set.
