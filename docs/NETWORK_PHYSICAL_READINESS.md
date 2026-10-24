# NETWORK_PHYSICAL_READINESS — LS5 Coordinator / PC4 Worker

**Decision: BLOCKED / NO-GO.** Source baseline: PR241 `b6139c3a8deaed9a590d2cb91e4daedef12da299`, PR244 `3808cb9f6ecd2f42d5d0c758145b427a58a010e8`. Historical tailnet addresses are **unverified**: LS5 100.103.160.110, PC4 100.91.48.20. No physical probes or service modifications were performed.

## Actual protocol and direction

| Initiator | Destination | Transport | Source-confirmed purpose | Required for physical G1? |
|---|---|---|---|---|
| PC4 Worker | LS5 Coordinator | authenticated HTTP API, proposed TCP/8765 | POST /enroll, /heartbeat, /ingest/minute, /ingest/event, /ingest/capture, /commands/{id}/result, ML claim/renew/artifact/finalize | Yes, but actual bind/port/TLS and ACL need approval |
| LS5 operator | PC4 SSH | Tailscale TCP/22 | optional administrative diagnostics | **Not required** for Worker protocol; separate owner approval |
| PC4 operator | LS5 SSH | Tailscale TCP/22 | optional diagnostics | **Not required** for Worker protocol |
| LS5 Coordinator | local isolated PostgreSQL | loopback, **dynamically approved unoccupied port** | enrollment tokens, credential hashes, command/ownership and ingestion persistence | Yes for DB-backed tests, but 55432 is reserved by hosted harness and not mandated |
| PC4 Worker | PostgreSQL | none | Worker is DB-less by design, sends authenticated ingestion to CONTROL | **DENY** |
| LS5 → PC4 | coordinator application port | none | No inbound Worker API endpoint required by reviewed heartbeat path | **DENY** |
| public/LAN/unapproved tailnet | LS5/PC4 test services | none | no external ingress | **DENY** |

Production `grid/config.py` defaults to `http://127.0.0.1:8765` and Bybit public URLs. A remote Worker requires a separately reviewed **non-loopback** Coordinator URL, TLS peer identity and route; do not reuse hosted CI's loopback-only `first_boot_policy` on two physical machines. Never start production `run_coordinator.py` with its wildcard 0.0.0.0 binding as a disposable G1 listener.

## Enrollment/auth/heartbeat

- `POST /enroll`: one-time token, row locked `FOR UPDATE`, expiry/used check; creates 48-byte URL-safe node credential stored as hash. Install mode derives from token, not Worker payload. **Duplicate node ID with same mode**: source uses `ON CONFLICT(node_id) DO UPDATE credential_hash`; a *new valid token* can rotate the node credential. This is not equivalent to rejecting duplicate identity; verify ownership and operator policy before G1.
- `node_auth`: valid per-node credential accepted; otherwise falls back to shared CONTROL token. CONTROL token must never be present on PC4. Cross-node impersonation using leaked CONTROL token is a high-severity design risk, not a demonstrated exploit in this audit.
- `POST /heartbeat`: PC4 initiates outbound every 10s by default, timeout 10s, redirects disabled. Worker sends `X-Node-Credential` **and** `X-Grid-Token` (possibly empty). Coordinator stores last_seen and returns symbols, micro_symbols, commands, control_replica, runtime_state, ownership and capture_evidence_protocol. For physical G1 require explicit empty CONTROL token on Worker and deny if it is populated.
- `GET /nodes/{node_id}/acceptance`: matching credential mandatory, accepts heartbeat age <= 2× interval. Scheduler considers alive <3× interval. Worker watchdog revokes stale assignments >=3× interval or expired ownership deadlines; delayed response is rejected if too old. These are **different** thresholds and need targeted tests.
- Coordinator keeps `nodes`, `assignments`, `instruments` in process memory; restart requires authenticated re-heartbeat and fresh assignment reconciliation. DB-backed ownership fences must prevent old collector_session or generation from regaining leases.
- Assignment uses weighted/stabilized scheduling, one owner per symbol, PILOT canary scope, NORMAL full universe, market state ACTIVE and ownership grant; Worker refuses workload unless granted and market_enabled.

## P0/P1/P2 negative tests (future isolated execution, real Worker required)

| ID | Pri | Repro scenario | Expected |
|---|---|---|---|
| N01 | P0 | PC4 Worker config contains nonempty CONTROL token | BLOCKED before start |
| N02 | P0 | Coordinator binds 0.0.0.0/:: or port conflicts with existing service | FAIL/STOP |
| N03 | P0 | PC4 attempts PostgreSQL 55432 or any DB socket | FAIL/STOP |
| N04 | P0 | Worker resolves production Bybit/production Coordinator URL in synthetic test | FAIL/STOP |
| N05 | P1 | Credential A used for node B heartbeat/ingest/acceptance | 401/403; no state mutation |
| N06 | P1 | Invalid/expired/replayed enrollment token; concurrent reuse | 401; exactly one token consumption |
| N07 | P1 | Same node_id re-enrolls with fresh valid token | Explicit rotation/rejection policy, revoke old credential; never two active identities |
| N08 | P1 | Network drop >2× then >3× heartbeat | acceptance false; assignments revoked; no live collector |
| N09 | P1 | Delayed heartbeat response >3× interval | response discarded; old grants not renewed |
| N10 | P1 | Coordinator restart + Worker reconnect | fresh heartbeat and fenced ownership; no duplicate assignments |
| N11 | P1 | Duplicate command ID and ingest message | durable receipt replay/idempotence; no repeated side effect |
| N12 | P1 | Reconnect storm, DNS mismatch, TLS invalid SAN, redirect | bounded retries, fail closed, no unauthorized fallback |
| N13 | P2 | Historical Tailscale IP/SSH host key no longer matches | UNKNOWN/BLOCKED until independent G0 readback |

Tests are **specifications, not executed physical or integration results**. Existing PR244 first-boot hosted tests must be independently checked at its exact HEAD and cannot substitute for Windows two-host TLS/firewall observations.

## Port selection without modifying existing services

G0 must observe listeners and service ownership on **both** machines. Reserve no port in this read-only task. Future G1 operator selects a newly owned high TCP port not present in either machine's listener inventory and not reserved by the integration harness (5432, 55432, 55433); holds the bound socket in the disposable child to avoid TOCTOU. Coordinator listens only on a reviewed approved Tailscale address or a separately reviewed authenticated TLS proxy. PostgreSQL listens on LS5 loopback only. No firewall opening or Tailscale ACL changes without separate authorization. If existing firewall blocks PC4→LS5, **BLOCKED**, not an invitation to open 8765.

## Evidence required for NETWORK_PHYSICAL_READINESS=READY

Owner-approved redacted G0 observations with current IP/host key/listener/service/firewall/Tailscale ACL identities; exact-source binary/certificate/secret custody; approved endpoint+port+TLS/credential contract; negative ingress tests; real Worker two-host heartbeat/reconnect/duplicate/replay/timeout and ownership evidence; raw JUnit/JSONL with HEAD/run/attempt and independent SHA256 readback. No mock Worker promotion. Until all are present: `NETWORK_PHYSICAL_READINESS=BLOCKED`, `physical_ready=false`, `execution_authorized=false`, `G1=NOT_AUTHORIZED`.
