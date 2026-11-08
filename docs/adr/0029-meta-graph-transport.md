# One Meta Graph transport under the Platform clients

Accepted, 2026-11-06 (user decision after the rate-limit work). Extends [ADR-0026](0026-inbox-connection.md) rule 6 ("one Meta Graph request function") from Instagram and Unified Login to every Meta call, WhatsApp included.

## Context

WhatsApp and Instagram are both Meta Platforms: they call the same Graph API (`graph.facebook.com/<version>`, Bearer token) and get back one error envelope (`error.code`, `error_subcode`, `error_data`, `fbtrace_id`) and the same usage headers (`x-app-usage`, `X-Business-Use-Case-Usage`). Wappa had two clients for it that disagreed. `WhatsAppClient` raised `httpx.HTTPStatusError` on any error and let each handler classify it, so a 5xx counted as a rejection, while Instagram's `InstagramGraphClient` / `graph_request` classified centrally and called a 5xx indeterminate. Meta's error code was parsed in three places, rejections were logged two ways (one of them printing a token prefix on a 401), and the rate-limit governor had to be wired into both clients. The architecture-hardening audit saw the Instagram half (area 06) but scoped `WhatsAppClient` out, so no area weighed the two side by side (plan H-34).

## Decision

1. **`wappa.messaging.meta.MetaGraphClient` makes every Meta API call.** It owns the versioned base URL, Bearer auth, outcome classification (accepted; rejected: a 4xx with Meta's code; indeterminate: transport failure, 5xx, or a 2xx that is not an error-free JSON object, never retried; rate_limited), Meta's error code (`meta_error_code`, parsed once), logging Meta's error fields without the token or an outbound Delivery Address echoed by diagnostics (rejections at ERROR, 5xx at WARNING), the shared `RateLimitGovernor`, usage headers and rewinding a retried upload. `graph_request` is its ungoverned core for calls made before an Inbox exists: Unified Login's code exchange and `debug_token` (`connections/meta_login.py`, with `token=None` when the call authenticates by query parameter) and Instagram field subscriptions. `MetaGraphClient.stream` is the one authenticated streaming GET, for media bytes from Meta's lookaside CDN; it is not classified or rate-governed, because the CDN is not the Graph API.
2. **Each Platform keeps its own client for its own concerns (SRP).** `WhatsAppClient` owns WhatsApp's URL shapes (`/{phone_number_id}/messages`, `/media`, `marketing_messages`) and the multipart form; `InstagramClient` owns Instagram's paths (`messages_path`, `attachments_path`) and its Messenger-family error wording (`describe_error`). Neither builds an HTTP request: both delegate to a `MetaGraphClient` they hold as `.graph`.
3. **Two calling styles, one classification.** `MetaGraphClient.request` returns a `GraphResponse` (Instagram's style). `MetaGraphClient.call` returns the accepted body or raises `MetaGraphError` (carrying the classified `GraphResponse`) or `RateLimitedError`, for WhatsApp, whose handlers map exceptions to results with `handle_whatsapp_error`. The decision is made once in `graph_request`; the WhatsApp handlers only read it.
4. **The shared code for an unknown outcome is `INDETERMINATE`** on every Platform (`message_outcome` reads it), replacing WhatsApp's `platform_outcome_indeterminate`.

GraphResponse.error_evidence and adapter result translators preserve native code/subcode and HTTP status separately from a neutral ErrorCategory. ErrorEvidence keeps retry safety distinct from temporary conditions; webhook errors use the same code mapping rather than HTTP-like numeric ranges. Historical error_code values remain unchanged, including WhatsApp symbolic tags.

## Consequences

- A Meta-level rule (rate limits, retries, logging, a Graph version bump) changes in one module, and a third Meta Platform (Messenger) reuses it unchanged.
- A WhatsApp 5xx is now `indeterminate` (it was a rejection), so it is never treated as a refusal that is safe to resend through another path.
- WhatsApp's Meta error log is the shared field summary (now including `error_data`) instead of the raw response body.
- Tests that faked `httpx.HTTPStatusError` from a WhatsApp client raise `MetaGraphError` instead; fake HTTP sessions implement `httpx.AsyncClient.request`.
- The token lives only in `MetaGraphClient` (requests and the media stream). The default `v26.0` and base URL have one source, `wappa/core/config/meta_application.py`; `WhatsAppUrlBuilder` still assembles `{base_url}/{api_version}/...` from the same values `MetaGraphClient.base` holds, a small remaining duplication.
- Reviewed after the extraction (two independent reviewers, 2026-11-06): no WhatsApp, Instagram or connection code calls the Graph API outside `MetaGraphClient` / `graph_request`. The one bypass found, `MetaBusinessLogin._request`, now uses `graph_request`.
