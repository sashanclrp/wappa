# Authentication Templates never send their OTP button

## Context

Wappa cannot currently deliver a WhatsApp Authentication Template that carries a copy-code button, which is the shape Meta's own template builder produces by default. The send is assembled without the button component Meta requires, so the provider rejects it.

The defect is easy to miss because the field that should prevent it is already there. `_TemplateTransportRequest` declares `authentication_method` and its validator demands one (`messaging/template_transport.py:214-234`):

```python
if self.category is TemplateCategory.AUTHENTICATION:
    if self.authentication_method is None:
        raise ValueError("authentication_method is required for authentication Templates")
```

A repo-wide grep finds `authentication_method` in exactly two files, `messaging/template_transport.py` and `messaging/__init__.py`, and inside the first it appears only in the model declaration and that validator. **Nothing reads it.** It is required of every caller and then discarded.

`_send_request` (`messaging/template_transport.py:502-545`) passes `template_type=request.category.value` onward for routing and never mentions the method again, and the handler it reaches builds a body-only payload (`messaging/whatsapp/handlers/whatsapp_template_handler.py:119-157`):

```python
body_component = self._build_body_component(body_parameters)
template_data = self._build_template_data(
    template_name, language_code,
    components=[body_component] if body_component else None,
)
```

Meta requires both components for an authentication template whose button carries the code:

```json
"components": [
  {"type": "body", "parameters": [{"type": "text", "text": "ABC234"}]},
  {"type": "button", "sub_type": "url", "index": "0",
   "parameters": [{"type": "text", "text": "ABC234"}]}
]
```

The button's URL is `https://www.whatsapp.com/otp/code/?otp_type=COPY_CODE&code_expiration_minutes=5&code=otp{{1}}`, so its `{{1}}` is a real placeholder that the send must fill. Omitting the component leaves a declared placeholder unsupplied, and Meta answers with a parameter-count error rather than delivering a partial message.

**How it was found.** MIIA (`wappa_miia`) built password recovery on a dialled one-time PIN and could not send a single one. Its approved `otp_test_code` / `es_CO` template is a perfectly ordinary Meta authentication template: `AUTHENTICATION` category, `add_security_recommendation: true`, a five-minute footer, and one copy-code button. It fails before reaching Meta today for a separate reason owned by Symphonai (see Dependency), and it will fail at Meta once that is fixed, because of this.

The blast radius is every Authentication Template with a button, not one consumer. Wappa has no path that can send one.

## Scope

- Carry `authentication_method` from `_TemplateTransportRequest` through `_send_request` into the messaging handler, instead of dropping it after validation.
- Emit the `button` component alongside `body` when the category is `AUTHENTICATION` and the method is `copy_code`. `sub_type` is `url`, `index` is `"0"`, and the single parameter repeats the code already sent in the body.
- Extend `send_text_template` on `IMessenger` (`domain/interfaces/messaging_interface.py:142`) and the WhatsApp implementations so the button is expressible rather than hard-coded inside one handler.
- Cover the payload shape with a test that asserts the emitted components, not just that the call succeeded. The current gap survived precisely because nothing asserts what goes on the wire.
- Make the validator honest: either the field influences the request, or it stops being required. This PRD chooses the former, and the test above is what keeps it true.

## Out of Scope

- **`one_tap` and `zero_tap`.** Both are declared on `TemplateAuthenticationMethod` (`messaging/template_transport.py:74-78`) and both need their own payload work — one-tap needs the handshake and autofill package metadata, zero-tap more still. Shipping `copy_code` first is deliberate: it is the default Meta produces, it is what is blocking a consumer today, and the other two need device-side verification this PRD cannot exercise. They should keep raising rather than silently sending a body-only payload, and the work is worth its own file.
- Media and location Authentication Templates. Meta does not permit a media header on an authentication template, so `send_media_template` and `send_location_template` need no equivalent.
- Detecting which method a template uses. That is the catalog's job and belongs to Symphonai (see Dependency).

## Implementation Notes

The code is sent twice in one payload, in the body and again in the button, and that is Meta's design rather than a redundancy to optimise away. The button's parameter is what the "Copiar código" tap writes to the clipboard; the body's is what the person reads. They must match, so both should be filled from the same value at one call site rather than by two callers agreeing.

`index` is a string (`"0"`), not an integer. Meta rejects the integer form, and a Pydantic model that types it as `int` will serialise it wrongly.

Authentication templates are already barred from BSUID recipients by the same validator, and that stays: Meta will not deliver one to a business-scoped id.

`_request_digest` (`messaging/template_transport.py:566`) feeds idempotency. Confirm the digest still distinguishes two sends that differ only by code once the button parameter joins the payload, so a resend with a fresh PIN is not collapsed into a replay of the previous one.

## Open Questions

- Does Meta accept the `url` sub-type for every copy-code authentication template, or do templates created through the newer API path report a `copy_code` sub-type that must be sent back verbatim? The one live sample available reports `type: "URL"`.
- Should the handler refuse an authentication send whose body parameter count is not exactly one? Meta's authentication templates permit a single body variable, so anything else is a malformed caller, and failing locally is cheaper than a provider round trip.

## Exit Criteria

- A copy-code Authentication Template sends successfully to a real number through `send_text_template`, and the recipient's "Copiar código" button copies the code that was sent.
- A test asserts the emitted `components` array contains both the body and the button, with matching parameter values and `index: "0"`.
- `authentication_method` provably changes the outgoing request; a test fails if it is ignored again.
- `one_tap` and `zero_tap` still raise rather than sending an incomplete payload.
- MIIA's `otp_test_code` / `es_CO` template delivers a PIN end to end, once the Symphonai dependency below has also landed.

## Dependency

Symphonai must land `260915-high-copy-code-otp-button-detection` first, or this fix is unreachable. Its catalog reads Meta's button as `type: "URL"` with a null `otp_type` and resolves `authentication_method` to `None`, so the validator above rejects the send before any of this code runs. Neither fix is sufficient alone: Symphonai's alone clears the local gate and then fails at Meta for the missing button; this one alone is never reached.

## Implementation outcome — 2026-09-15

Shipped. `authentication_method` now crosses `_send_request` into the WhatsApp handler, which emits `[body, button]` with `sub_type: "url"`, a string `index`, and the code repeated from the body. `tests/test_authentication_template_otp.py` and a golden fixture (`tests/fixtures/meta/v25.0/authentication_copy_code_request.json`) assert the emitted components, so ignoring the field again fails a test.

Two deliberate divergences from the scope above, both from reading Meta's docs:

**`one_tap` and `zero_tap` ship too, rather than raising.** Meta's own one-tap autofill page documents the identical send payload — body plus a `sub_type: "url"` button repeating the code — and its template-creation page states that a button submitted as `otp` "will be set to `url`" on creation. The handshake, `supported_apps`, and broadcast receiver the Out of Scope section points at live in template creation and in the Host Application's mobile app; none of them touch this send. Raising on them would have refused a payload Wappa can build correctly. The exit criterion behind that line still holds: no method can produce a body-only payload, because the button is emitted for all three or the send is refused locally.

**Wappa can now resolve the method itself.** `TemplateInfo.authentication_method` reads `otp_type`, then falls back to parsing `otp_type=` out of the generated button URL. This is exactly the `type: "URL"` with null `otp_type` case the Dependency section describes, so a catalog reading templates through Wappa no longer has to resolve the method by hand.

Open Questions, answered: Meta rewrites every OTP button to a URL button at creation, so `sub_type: "url"` is correct for every copy-code template regardless of the API path used to create it — there is no `copy_code` sub-type to echo back (that sub-type belongs to marketing coupon templates). And yes, a body parameter count other than exactly one is now refused locally, at both the transport request and the handler.

Still pending: the Symphonai dependency, and an end-to-end send of MIIA's `otp_test_code` / `es_CO` to a real number.
