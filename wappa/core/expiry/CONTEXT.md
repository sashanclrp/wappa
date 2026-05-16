# Expiry Context — Glossary

Terms specific to the `wappa.core.expiry` bounded context. Shared Wappa kernel terms (`inbox_id`, `Inbox`, `Host Application`, etc.) are defined in the root `CONTEXT.md` and are not repeated here.

| Term | Definition |
|---|---|
| **Expiry Action** | A named, time-triggered side-effect registered by a host application. Fired when a Redis Expiry Key expires. Registered via the `@expiry_registry.on_expire_action("<name>")` decorator. |
| **Expiry Key** | A Redis key with a TTL whose sole purpose is to schedule an Expiry Action. Format: `{inbox_id}:EXPTRIGGER:{action}:{identifier}`. The key carries no payload; all routing information lives in its name. |
| **Trigger Prefix** | The literal segment `EXPTRIGGER` that marks a Redis key as an Expiry Key and distinguishes it from operational cache keys. |
| **Action Name** | The third colon-segment of an Expiry Key (e.g., `payment_reminder`). Used as the lookup key when resolving a handler from the registry. |
| **Identifier** | The fourth colon-segment of an Expiry Key. Carries a user- or entity-specific value (e.g., a phone number or transaction ID) passed verbatim to the handler. |
| **Expiry Event** | The parsed, structured form of a Redis keyspace notification. Holds the expired key, resolved handler reference, identifier, and action name. Produced by `ExpiryEventParser`, consumed by `ExpiryDispatcher`. |
| **Keyspace Notification** | A Redis pub/sub message on `__keyevent@{db}__:expired` that fires when any key in that database expires. The expiry listener subscribes to this channel. |
| **Expiry Listener** | The long-running async task (`run_expiry_listener`) that subscribes to Redis keyspace notifications and orchestrates the parse → dispatch pipeline. |
| **AppContext** | A singleton container that holds a reference to the host application's `FastAPI` instance, giving expiry handlers access to shared state (e.g., HTTP session) without global variables. |
| **ExpiryContextError** | Base exception hierarchy used when an expiry handler cannot bootstrap required dependencies (messenger, cache factory, FastAPI app, HTTP session). |
