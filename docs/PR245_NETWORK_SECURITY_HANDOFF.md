# PR245 security compatibility handoff — NETWORK_PHYSICAL_READINESS

Exact source comparison: PR241 `05df07df2d391c3b7c96956c1b4ac5fce8ec29a7`; PR244 `79049906cb004e324bec5ef4cc53b85381cab83a`; PR245 `0892a1c850787d024a782ff3e44286c191529232`. Read-only review; no merge or physical activity.

## JSON limit semantics

The parser must accept **only exact `str`** (not `bytes`, `bytearray`, `dict`, subclasses), reject >65536 **UTF-8 encoded bytes** before JSON decode, and handle unpaired Unicode surrogates via `UnicodeError`. A 65536-byte input passes *size admission only*; malformed JSON, duplicate keys, nonfinite numbers, unexpected fields and unsafe network policies remain BLOCKED. The parser never returns execution authorization or host verification.

Minimal patch for #244 from #245 (Codex to apply on current #244 HEAD, **not** a merge of #245): in `installer/ls5_network_offline.py`, inside `evaluate`'s try before `json.loads`, reject `type(raw) is not str` or `len(raw.encode('utf-8')) > 65536`; include `UnicodeError` in the fail-closed exception tuple. Retain `object_pairs_hook=_unique`, `parse_constant=_reject_constant`, generic `INVALID_POLICY` and all authority flags false. Do not alter physical observation parser's independent limits.

Minimal offline negative matrix (expected `policy_valid=false,status=BLOCKED,execution_authorized=false`):
- `None`, `b'{}'`, `bytearray(b'{}')`, `{}`, `[]`, numeric input
- `' '*65537`, `'é'*32769`, `'😀'*16385`
- unpaired `'\\ud800'`, `'\\udfff'`, `'{"x":"\\ud800"}'` as literal Python surrogate
- duplicated `security` key, `NaN` / `Infinity`, extra authority fields, unsafe bind
- exactly 65536 ASCII bytes: assert **no size error**, but still BLOCKED for invalid JSON; boundary admission must not be confused with physical readiness
- self-consistent syntactically valid model remains `policy_valid=true` and `status=BLOCKED`.

## Enrollment, credential and role boundaries

Source `grid/enrollment.py`: token consumed atomically under `FOR UPDATE`; existing same-mode node ID can receive new credential via `ON CONFLICT(node_id) DO UPDATE credential_hash`. This is credential **rotation**, not duplicate-ID refusal. Race/replay test must assert exactly one token use and old credential invalidated after a legitimate new enrollment; owner authorization to rotate node identity is a separate missing policy gate.

Source `grid/coordinator.py`: `node_auth` accepts per-node credential or fleet CONTROL token fallback. Source `grid/worker.py`: heartbeat sends both `X-Node-Credential` and `X-Grid-Token` from settings. For physical PC4, require CONTROL token absent/empty and test that a wrong node credential cannot access node B. Removing CONTROL fallback requires review of all routes using `node_auth` and existing agent compatibility, not an unreviewed one-line patch.

Worker `run()` sets `self.db=None`; ingestion uses authenticated Coordinator API. **No PC4 PostgreSQL DSN, database role, PG credentials or direct TCP/55432 permission**. Check environment/child process and evidence for leaks; source intent alone does not prove Windows token privileges.

## Allowed network flow matrix (future G1; not authorized)

| Source | Destination | Service | Proposed policy |
|---|---|---|---|
| PC4 Worker | LS5 Coordinator | approved TLS API port (8765 only if free and owner approved) | allow narrowly, Tailscale identity + firewall + TLS + node credential |
| LS5 Coordinator | LS5 isolated PostgreSQL | approved loopback port, **not necessarily 55432** | allow local only |
| LS5 operator | PC4 SSH/22 | optional administrative channel | deny unless separately approved |
| PC4 | LS5 SSH/22 | optional diagnostics | deny unless separately approved |
| PC4 | LS5 PostgreSQL/55432 or any DB port | direct DB | **DENY** |
| LS5 Coordinator | PC4 Worker API port | none needed for heartbeat protocol | **DENY** |
| public/LAN/unapproved peers | LS5/PC4 test ports | any | **DENY** |
| physical test Workers | production Bybit or production Coordinator | any | **DENY** |

G0 must independently establish current Tailscale IPs, host identity, effective firewall, listener process, occupied ports, TLS certificate and secret custody. Historical IPs are not permission. No `0.0.0.0` binding or opening new firewall ports without separate approval.

## Required Codex evidence and status

Use real Worker processes with disposable PostgreSQL and synthetic market feed; test concurrent enrollment, duplicate node ID, old credential invalidation, wrong-node auth, CONTROL fallback refusal policy, stale heartbeat at >2× and assignment expiry at >=3× interval, delayed reply, restart and replay. Require exact HEAD/run/attempt, zero-skip JUnit, JSONL, SHA256 raw artifact inspection, independent reviews and separate G1 approval. **NETWORK_PHYSICAL_READINESS=BLOCKED; Physical PC4 0/10 NOT_RUN; Execute NOT_AUTHORIZED; Deployment NO-GO.**

## Updated PR244 G0/CI checkpoint

PR244 advanced to exact `576e77086f645ac9eb3b0d26a43fc967155d24da`. The 65,536-byte and UnicodeError guards are now present in its `installer/ls5_network_offline.py`, so the previous **missing-code incompatibility is resolved by source inspection**. Hosted full-system workflow `40112870668` and preflight `40112870681` report SUCCESS at that HEAD; their raw artifacts have not been independently rehashed in this review. PR241 `e96b7e8dde6c9927376f6311d6d08d52e705b144` network run `40111254326` and preflight `40111254297` also report SUCCESS. None authorizes G1.

Coordinator Issue #243 now contains an **author-reported** G0 metadata collection for LS5 and PC4 on the same PR244 HEAD/run. Reported existing PostgreSQL wildcard listeners: LS5 TCP/55432 PID5472 and PC4 TCP/5432 PID7028. These are not independently witnessed or process-identity-attested. **Treat both ports as occupied/unowned and do not connect, adopt, stop, restart, reuse or reconfigure those listeners.** This supersedes any previous suggestion that TCP/55432 is available for a disposable LS5 PostgreSQL instance. Exact future G1 ports require independent native owner review and reservation under a separately approved executor. Current effective firewall/Tailscale/TLS, process custody, DB roles and egress remain UNKNOWN.

Additional fail-closed negative input: deeply nested JSON can raise `RecursionError` even below the 65,536-byte cap. PR241 now catches it and tests nested arrays/objects. Codex should independently review this minimal exception handling and add the same regression to PR244 only after verifying its actual parser behavior. Do not broaden the exception handler to indiscriminate `Exception`.
