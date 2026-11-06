---
checked_on: 2026-11-05
checked_against: Meta Instagram API with Unified Login authentication and get-started pages (Graph v26.0) and Wappa's tests/test_instagram_connection.py
revision: 2
---

# Unified Login, credentials and extensions

## Contents

- Self-service connection
- Persist, refresh, rotate, revoke
- Trusted credential access
- Host-initiated sends
- Extension webhook fields

## Self-service connection

Connecting an account is the `IInboxConnector` contract (ADR-0017), the same on every Platform: `InstagramConnector` (Unified Login) and `WhatsAppConnector` (Embedded Signup) implement it. The Host owns the routes, the authenticated operator, intent storage, the Owner/Channel mapping and transactions.

```python
from wappa.connections import InstagramConnector, MetaLoginConfig

connector = InstagramConnector(
    MetaLoginConfig(app_id=META_APP_ID, app_secret=meta.app_secret, config_id=CONFIG_ID,
                    redirect_uri=f"{BASE}/connect/instagram/callback"),
    client_provider=lambda: http_client,
    intent_store=host_intent_store,   # IConnectionIntentStore: atomic, one-use consume()
)
auth = await connector.begin(host_subject=operator_session_id)      # redirect to auth.url
grant = await connector.complete(state=state, host_subject=operator_session_id,
                                 code=code, error=error, error_reason=error_reason)
for inbox in grant.inboxes:          # DiscoveredInbox: inbox_ref, account_ref, display_name
    ready = inbox.readiness           # conversation_ready, features={"comments": ...}, scopes
```

`complete` consumes the state before exchanging the code, so a replay, an expired attempt or a different operator raises `ConnectionStateError`. A cancelled dialog raises `ConnectionCancelledError`, and a provider refusal raises `ConnectionProviderError(code)`. Instagram accounts come from `/me/assigned_instagram_accounts`; `/me` is the system user, never an Inbox. Missing optional scopes do not block messaging. `InMemoryConnectionIntentStore` is for single-process examples only. Swap in `WhatsAppConnector` with an Embedded Signup `config_id` and the same code connects WhatsApp numbers.

## Activate, persist, refresh, revoke

```python
runtime = app.state.inbox_runtime
activated = await connector.activate(grant, inbox.inbox_ref,
                                     credentials=runtime.credential_service,
                                     previous=existing_record)  # rotates when present
host_store.put(activated.record)                              # 1. Host commit
await runtime.directory.refresh_inbox(inbox.inbox_ref)        # 2. then refresh Wappa
# activated.webhooks_subscribed, activated.details (per-field outcomes)
```

Refuse to silently reactivate an inactive (revoked) record. Wappa mounts no deauthorize route: that callback fires only for Instagram Login grants, which Unified Login never creates. A Host data-deletion callback posts a `signed_request`; verify it with `parse_signed_request(value, app_secret)`. To revoke, store `credential_service.create_inactive_record(record)` and refresh. To stop webhooks, call `connector.disconnect(record.inbox_ref, record.account_ref, token)`. After rotation or deactivation, the next resolution sees the change; in-flight calls are not cancelled.

Unified Login (Facebook Login for Business) issues business-owned `SYSTEM_USER` tokens that never expire, and Meta sends no per-user deauthorize for them. Revoke those through the business portfolio's system user or the Host's connector (deactivate the record, then `connector.disconnect`).

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
