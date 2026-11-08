# Expiry Context — Architecture

## Responsibilities

This context runs Redis expiry work through the shared scheduled lane. Pub/Sub provides prompt notification; a durable due-time index in the same expiry database recovers occurrences missed during Wappa restarts, deploys, crashes or notification outages. Every indexed occurrence whose TTL key is gone remains pending until the Host handler succeeds. Delivery is at least once while Redis retains its data; Hosts retain idempotent fences.

It parses qualified Expiry Keys, asks the Host's `ExpirySubjectBinding` for a User or Inbox-only subject, and schedules tracked work through `Scheduling.run`. It owns bounded recovery and Pub/Sub reconnection, not business logic, general recurrence, external scheduler storage or execution history. Memory and JSON remain without timer engines.

## Modules

| Module | Responsibility |
| --- | --- |
| `listener.py` | Run independent Pub/Sub reconnect and recovery tasks; cancel source tasks on shutdown while tracked handlers drain. |
| `parser.py` | Parse `{inbox_namespace}:EXPTRIGGER:{action}:{identifier}`; invalid namespaces never acquire a fabricated scope. |
| `recovery.py` | Admit Pub/Sub and index work through one path, with at most 100 in-flight indexed deliveries per process; query at most the remaining capacity per tick. |
| `dispatcher.py` | Build `ScheduledEvent`, run the subject binding and handler, and acknowledge only after successful completion. Failed/cancelled/draining work stays pending. |
| `connection.py`, `reconnection.py` | Pub/Sub subscription, configuration and bounded reconnect backoff; exhausted Pub/Sub reconnect attempts do not disable index recovery. |
| `wappa/persistence/redis/expiry_index.py` | Redis Lua operations for atomic arm/renew, cancel, rebind, due reads, short claims and generation-fenced acknowledgments. |

## Durable pending occurrences

`RedisExpiry.set` atomically writes the TTL key, a sorted-set member in `__system__:expiry:due`, and a record in `__system__:expiry:records`. Members are complete Inbox-qualified Expiry Keys, so action/identifier and Platform/Inbox scope remain explicit. Records retain an opaque generation and original due time; both deadline and eligibility use Redis TIME. These keys have no TTL. The sorted set is shared by this expiry database so workers discover due work without listing Inboxes or scanning keys. It is pending work, not a Run/history archive.

The first recovery tick runs immediately at listener startup, then every two seconds. Each tick reads at most 100 due members, reduced by that process's in-flight count, using ZRANGEBYSCORE LIMIT. Claim Lua checks that the key is absent and the occurrence is eligible, then defers its index score by a 30-second claim deadline. Multiple workers can race safely at admission; a crashed worker's claim becomes eligible again. Long handlers can outlive the claim and be invoked concurrently in another worker. Exactly-once delivery is not promised.

Successful handler completion removes the index member and record only if the original record still matches and no renewed TTL key exists. An old delivery therefore cannot delete a replacement generation, even if its key has already expired. Handler, binding or acknowledgment failures retain pending work for another claim. Failed work's deferred score lets other due members progress. The index does not require keyspace notifications to be enabled or the Pub/Sub connection to be healthy.

Cancel atomically removes the TTL key and pending occurrence, including when the key is already gone. Cancel-by-identifier uses bounded HSCAN batches for pending records and SCAN for old unindexed keys, never KEYS. Rebind atomically moves a live TTL key and its record/index member, retaining the due time and generation; a live or pending destination is a conflict. It returns false after the source TTL key is gone. Cancellation/renewal cannot undo a handler already admitted: the Host's fences remain authoritative.

## Dispatch and lifecycle

Both paths use `ExpiryDispatcher` → `ScheduledEvent(source="redis_expiry")` → `Scheduling.run` → `DispatchContextBuilder.scope` → `handle_scheduled_event` → `process_scheduled_event`. Indexed events carry their original UTC `scheduled_for`, the occurrence generation as correlation `execution_id`, and metadata `expired_key` plus `recovered`. Index/tick deliveries set `recovered=true`; direct Pub/Sub deliveries set false. Payload remains empty. The flag describes the admission path; it is not an exactly-once or timing assertion. Subject resolution is unchanged and never infers a User from an identifier.

SchedulingPlugin starts the expiry source at priority 95, after ordinary Redis/database/Host startup hooks, so startup recovery does not capture incomplete dispatch capabilities. Shutdown stops trigger admission before draining tracked handlers and closing pools. No source task owns a detached handler task.

## Upgrade boundary

Keys armed before this upgrade have no durable index entry. Their live Pub/Sub notifications still dispatch, but missed pre-upgrade expirations cannot be reconstructed. For still-live qualified keys, `wappa migrate expiry-index --redis-url ...` adds recovery metadata without changing the value or remaining TTL (dry run unless `--apply`). Expired unindexed keys cannot be recovered. An explicit rebind of a live legacy key indexes its remaining TTL. Unindexed notifications have no known due time or occurrence generation. Retaining Redis data and an active SchedulingPlugin(redis_expiry=True) are prerequisites for recovery; Redis data loss is outside this guarantee.

The migration uses SCAN and one atomic snapshot/write per valid key in `wappa/persistence/redis/expiry_migration.py` and `RedisExpiryIndex.index_existing`. Existing complete records remain unchanged; partial or malformed records are conflicts. Reserved index keys have no TTL and are protected by generic cache delete/expire/rename operations; pool shutdown only closes connections. Redis retention/eviction configuration remains deployment-owned. See `docs/migration/0.34.7.md`.
