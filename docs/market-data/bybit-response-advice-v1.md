# Bybit response advice v1 — pure, untrusted, not admitted

`grid.bybit_response_advice.parse_response_advice` interprets a bounded explicit
response projection. No provider client, clock read, timer, persistence, quota
counter, retry/send, scope resolution or authority mechanism exists. Output
`authority_status` is always UNTRUSTED_ADVICE_ONLY. There is no PERMIT, allowance,
deadline or quota delta. Parsed data cannot activate any of the six disabled
provider-policy operations or resolve an UNKNOWN dispatch attempt.

Exact typed profile is `tests/fixtures/agent3-bybit-response/profile.json`;
`PROFILE_SHA256` hashes its canonical complete bytes. It is a new advice profile,
not an implicit conversion to the frozen provider policy or EgressProjection.
No shared consumer is wired. A1 exact compatibility ACK is required first.

## Bounds and representation

HTTP status is exactly a decimal string100..599. Headers are a list of at most5
two-string lists, only Retry-After, Date and three X-Bapi rate headers. Names
max64ASCII bytes, values max256, no control characters or padding. Header names
are HTTP case-insensitive; duplicate names reject even with identical values.
Unknown full-response headers reject: an actual transport must explicitly form
this allowlisted projection preserving duplicates and retain original evidence;
never silently discard conflicts or truncate to this bound. Header integers use
canonical unsigned decimal strings <=9007199254740991. Remaining>limit rejects.

Body is actual raw bytes <=4096; empty is allowed as unknown. A nonempty body must
be a bounded ASCII error JSON object with integer retCode0..2147483647 and string
retMsg<=256; exact plain403 `access too frequent` is separately recognized. Depth8,
object members32, nodes including keys128; duplicates/nonfinite/floats reject.
retCode's JSON integer is an explicit versioned provider-to-advice projection to
a decimal string, not old-domain/C3 financial coercion. No body truncation or
generic success payload parsing. Large/unsupported bodies yield format error;
consumer must fail closed, never ignore it as success. Individual bounds do not
grant compliance with a different consumer's aggregate projection-size cap.

Complete raw body SHA and original projected header-list SHA are retained. Those
hashes identify input bytes only, not actual receipt, NAT identity, authorization,
dispatch ownership, dedup identity or trusted observation provenance.

## Signals, not permission

- HTTP429: system frequency signal, advisory minimum1second.
- HTTP403 with exact case-insensitive access-too-frequent message: IP frequency
  ban guidance minimum600seconds, HTTP-session containment required. Generic403
  remains ambiguous, without a guessed automatic recovery time.
- retCode10006 outside403/429: API UID/endpoint throttle, minimum1second. This
  never infers public-IP scope. Mixed status/code remains visible in both fields.
- Other responses, including high remaining values, say NO_RECOGNIZED_THROTTLE;
  that is not a send grant or a statement that budget is available.

Retry-After unsigned seconds can only tighten an existing advisory minimum.
Exact IMF-fixdate is retained without clock resolution. Date is untrusted too.
X-Bapi reset is retained as bounded endpoint/UID Unix milliseconds, never a
public-IP reset or worker-clock deadline. Timestamp values beyond9999 reject;
even a structurally valid future reset needs actual authority/time review before
any ledger interpretation. Missing headers never clear persistent cooldown.

Actual A1/A2 ledger must independently verify source/scope/attempt identity, dedup,
current policy/authority time, persistent cooldown/adaptive revisions and sender
containment before any atomic transition. Parser output is never fed directly
to dispatch, a timer or storage. Restart/retry/debit enforcement remains NOT_RUN.

Official facts checked2026-11-07:
https://bybit-exchange.github.io/docs/v5/rate-limit
https://bybit-exchange.github.io/docs/v5/error
Retry-After handling is a conservative parser feature, not a claim Bybit always
supplies that header. Source qualification is documentation plus offline fixtures;
no real API requests, provider admission or native/runtime acceptance.
