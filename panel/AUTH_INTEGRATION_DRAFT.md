# HTTP auth integration (#426)

`server.py` now lazily loads the gate only when `YUVA_AUTH_ENABLED=1`; auth is
off when the setting is absent or `0`. Enabling requires a pre-provisioned
store and matching audience. There is no bootstrap or enrollment endpoint.
Verifier records must be provisioned by a trusted host-console process.

## Route contract

Every listed route is `POST`. In enabled mode, its signature scope is exactly
`POST <canonical route>`. The trusted principal comes only from successful
HMAC verification; request body identity and role fields never establish it.

| Route | Existing effect | Enabled-mode rule |
|---|---|---|
| `/api/katil` | Adds or updates roster/presence fields and may append a status message | Provisioned principal must match body `kimlik`; non-admins can only use the default `isci` role |
| `/api/kalp` | Heartbeat endpoint; currently returns 503 without a verified broker source | Principal must match `kimlik`; this draft does not remove the existing 503 safety gate |
| `/api/ayril` | Marks a roster member disconnected and appends a status message | Principal must match body `kimlik` |
| `/api/ad` | Renames a roster member and may append a status message | Self rename or operator-configured admin principal |
| `/api/rol` | Changes role / head-inspector assignment and appends a status message | Operator-configured admin principal |
| `/api/sorumlu` | Changes a roster responsibility link | Operator-configured admin principal |
| `/api/bas-denetci` | Changes the head-inspector assignment | Operator-configured admin principal |
| `/api/yaz` | Appends a message to the Yuva bus | Use verified principal as actor; do not accept body `kimden` as identity |
| `/api/ekran` | Appends a screen/event record | Principal must match body `kimlik` |
| `/api/not` | Writes a roster note; currently unused | Remains closed, including for otherwise valid route credentials |
| `/api/gorev` | Bridges task workflow operations to `bin/yuva` | `ekle`/`ata`/`iptal`: configured admin; `al`/`sonraki`/`teslim`: worker principal plus Yuva role/ownership checks; `ilk-kontrol`/`denetle`: reviewer principal plus Yuva role/state checks |

The admin principal set must come from trusted operator-managed configuration,
not from `durum.json` role claims, request fields, or a message's `kimden` value.
The existing auth verifier's exact route scopes still apply before these
additional principal rules.

## Optional GET snapshot read-scope prototype

`AuthGate` also exposes a separate `GET_ROUTE_POLICY` and
`authenticate_get(request_target, headers, raw_body)` / `authorize_get()` pair
for `/api/veri` and the compatibility alias `/veri`. This path is off unless
the caller explicitly constructs `AuthGate(..., read_enabled=True)` with an
HMAC verifier. Each path requires its own exact scope (`GET /api/veri` or
`GET /veri`); POST scopes do not authorize reads. The raw target must equal the
route exactly, query/fragment/aliases are rejected, and the request body must
be empty. Successful verification consumes the HMAC nonce through the shared
verifier store.

This remains a code prototype: `server.py` does not call it and no
`YUVA_AUTH_READ_ENABLED` startup flag is implemented. The caller must reject
GET transfer framing/non-empty bodies before snapshot generation, authenticate
before reading/serializing `/api/veri`, and dispatch the same exact route.
`/` and `/index.html` are outside this allowlist. Browser HTML must not contain
an HMAC secret; browser session authentication, cache policy, read rate limits,
and deployment rollout require separate decisions. Disabled `authenticate_get`
returns `None` for legacy behavior, which is not authentication evidence.

## Required handler order

1. Keep Host/Origin/content-type and bounded `Content-Length` checks.
2. Read the bounded raw body, then authenticate before JSON parsing or endpoint
   invocation. Reject duplicate/missing auth headers. Sign and dispatch only
   the exact route path: query strings, trailing slashes, aliases, and other
   noncanonical targets are rejected so the signed target cannot differ from
   the route selected by `UCLAR`.
3. Parse JSON only after a valid signature and consumed nonce. Apply the
   route-specific body/principal binding before calling the endpoint.
4. Convert every `AuthError` to its explicit HTTP status and stop processing.
   In particular, 401/403/503 must not call a local CLI fallback or endpoint.
   Do not catch auth/store errors as transport errors.
5. Pass the verified principal separately to message/event writers. Keep
   endpoint mutation atomicity and domain-operation idempotency as separate
   concerns; consuming a nonce does not make a retried mutation idempotent.

The server reads `YUVA_AUTH_STORE_ROOT`, `YUVA_AUTH_AUDIENCE`, and optional
comma-separated `YUVA_AUTH_ADMIN_PRINCIPALS` when enabled. The store root and
its snapshot/lock must already be provisioned securely. Missing, malformed, or
unreadable configuration stops startup; it never falls back to anonymous mode.
The authenticated principal is passed separately to actor-sensitive handlers
and writers. The store's generation is not anchored outside the store, so
restoring an older valid snapshot remains an operational anti-rollback risk.
