# Plugins Context Glossary

Terms specific to the plugin system. Shared kernel terms (`inbox_id`, Host Application, `WappaEventHandler`) are defined in the root `CONTEXT.md`.

| Term | Definition |
|------|------------|
| **Plugin** | A composable unit that extends a Wappa application by registering middleware, routers, and lifecycle hooks through `WappaBuilder`. Implements the `WappaPlugin` protocol. |
| **WappaPlugin** | The structural protocol (three methods: `configure`, `startup`, `shutdown`) that every plugin must satisfy. Checked by structural typing — no inheritance required. |
| **configure phase** | The synchronous build-time step where a plugin calls `WappaBuilder` methods to register middleware, routers, and hooks. Runs before the FastAPI app is instantiated. |
| **startup hook** | An async callable registered with a priority integer that runs during the FastAPI lifespan startup sequence. Lower numbers run first. |
| **shutdown hook** | An async callable registered with a priority integer that runs during shutdown. Higher numbers run first on the way down (reverse of startup). |
| **priority** | An integer that controls hook or middleware execution order. Convention: 10 = core, 20 = infrastructure (Redis, DB), 25 = listeners/expiry, 30 = application services, 50 = user-defined default. |
| **messenger middleware** | A cross-cutting async callable that wraps every outbound `IMessenger` call. Registered via `add_messenger_middleware` with a priority band. |
| **SSEEventHub** | The in-process fanout broker owned by `SSEEventsPlugin` that holds per-client async queues and distributes real-time events to SSE subscribers. |
| **expiry listener** | A long-running background `asyncio.Task` started by `ExpiryPlugin` that subscribes to Redis keyspace expiry notifications and dispatches expiry actions. |
| **External Webhook Source** | A non-messaging system that sends webhooks into Wappa, such as MercadoPago, Stripe, Wompi, GitHub, or a CRM. |
| **processor mode** | The operating mode of `WebhookPlugin` in which an `IWebhookProcessor` handles an External Webhook Source and produces an `ExternalEvent`. |
| **raw handler mode** | Legacy operating mode of `WebhookPlugin` in which a plain callable processes the request with no Wappa infrastructure. Target for removal in the clean-break compatibility cleanup. |
| **PubSub channel** | The Redis channel pattern (`wappa:notify:{inbox_id}:{user_id}:{event_type}`) used by `RedisPubSubPlugin` to broadcast real-time event notifications. |
| **AuthStrategy** | An abstract strategy object encapsulating a single authentication scheme (Bearer, Basic, JWT, or custom) that `AuthPlugin` passes to `AuthMiddleware`. |
