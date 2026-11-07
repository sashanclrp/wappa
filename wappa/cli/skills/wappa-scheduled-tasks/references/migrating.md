# Moving existing code to the hook

This covers scheduled code only. Upgrading to 0.34 changes much more, so follow the `wappa-host-integration` skill's upgrading reference for the rest. There are no aliases, so do this part in one change. The installed `CHANGELOG.md` lists every removed name, and section 21 of the [migration guide](https://github.com/sashanclrp/wappa/blob/main/docs/migration/v0.34.0-from-0.33.md) has the full table.

## Contents

- Order of work
- Name map
- Behavior that changes
- Already-armed triggers

## Order of work

1. List every action: `expiry_registry` handlers, crons and scheduler job bodies. For each, write its source, scope and what its identifier really is.
2. Write `process_scheduled_event` with one `case` per action. Move handler bodies behind it, unchanged at first.
3. Delete the capability construction from each body: Inbox parsing, Messenger and cache factories, `sse_event_scope`. Read `self.inbox_ref`, `self.user_id`, `self.messenger` and `self.cache_factory`.
4. Build shared typed dependencies once at the top of the hook, replacing per-feature assembly. A shared wrapper the hook calls is fine.
5. Replace the plugins with one `SchedulingPlugin` and add the `expiry_subjects` binding from your list.
6. Point scheduler job bodies at `Scheduling.from_app(app).dispatch(...)`. Keep registration, stores and policies exactly as they are.
7. Search for the removed names until none remain, then run your tests and one real firing per source.

Keep Host guards where they matter: admission checks, leases, send fences and generation checks move into the hook or its callees. Wappa doesn't replace them.

## Name map

| Before | After |
| --- | --- |
| `ExpiryPlugin()` | `SchedulingPlugin(redis_expiry=True, expiry_subjects=...)` |
| `CronPlugin(handler)`, `.add_cron(cron_id, ...)` | `SchedulingPlugin()`, `.add_cron(action, ...)`; the other `add_cron` arguments are unchanged |
| `CronPlugin(include_router=, config=)` | `SchedulingPlugin(include_cron_router=, cron_config=)` |
| `@expiry_registry.on_expire_action("x")` | `case "x":` in `process_scheduled_event` |
| `(identifier, full_key)` arguments | `event.identifier`, `event.metadata["expired_key"]` |
| `process_cron_event(event)` | `process_scheduled_event(event)` |
| `event.cron_id`, `event.cron_expr`, `event.tags`, `event.timestamp` | `event.action`, `event.metadata["cron_expr"]`, `event.metadata["tags"]`, `event.dispatched_at` |
| `parse_inbox_ref_from_expired_key(full_key)` | `self.inbox_ref` |
| `create_expiry_messenger(inbox_ref)` | `self.messenger` |
| `create_expiry_cache_factory(inbox_ref, user_id)` | `self.cache_factory` |
| `get_app_context().get_app()` | Your own app reference |

## Behavior that changes

- **An identifier isn't a User unless your binding says so.** Without a binding, `self.user_id` and `self.cache_factory` are `None`.
- **Your resolver now runs for you, and its failure stops the task.** Delete manual canonicalization. If an unresolvable identifier should still fire, catch the failure inside the resolver.
- **Every valid trigger reaches the hook,** not only registered ones. Handle leftover actions.
- **Cron failures propagate.** They used to be logged and swallowed, so `max_retries` now takes effect, and a silently failing cron starts surfacing.
- **Inbox-only crons have their Messenger.** Remove any workaround.
- **SSE stops guessing.** `bsuid` and `phone_number` are no longer classified from the identifier. Call `update_identity` if subscribers read them.
- **A handler that swallowed its exceptions can stop.** For expiry, Wappa logs a raised exception with the action and identifier.

## Already-armed triggers

`wappa migrate cache-namespaces` renames still-live Expiry Keys and keeps their TTLs, so a trigger armed by the old version fires into the new hook when it expires. An expiry missed while no listener ran is not replayed. Before deploying, make sure your binding and hook recognize every action that might still be armed. For a retired one, return `None` from the binding and add a no-op `case`; a raised binding error also drops the trigger, but logs an error.
