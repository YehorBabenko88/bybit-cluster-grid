# First isolated coordinator/agent network contract (source review, 2026-10-24)

**Status: BLOCKED for integrated PASS.** Based on `grid/coordinator.py`, `grid/enrollment.py`, `grid/config.py` at PR #241 base lineage; not a claim of agent integration or PostgreSQL runtime execution. Codex must use the **existing repository agent**; do not substitute a mock as proof of production-agent behavior.

## Observed coordinator HTTP contract

| Method | Path | Input/auth | Expected |
|---|---|---|---|
| GET | /health | no credential in route signature | health snapshot; **not** readiness/auth proof |
| POST | /bootstrap/envelope | `X-Grid-Token`, CONTROL role | enrollment envelope; admin-only |
| POST | /enroll | JSON `enrollment_token,node_id` | JSON `node_id,credential,install_mode`; invalid/expired token 401 |
| POST | /heartbeat | JSON `node_id`, `X-Node-Credential` **or** `X-Grid-Token` fallback | `symbols,micro_symbols,commands,control_replica,live_mode,install_mode,runtime_state,ownership_protocol,ownership` |
| GET | /nodes/{node_id}/acceptance | `X-Node-Credential` for matching node | accepted false if never seen; stale when heartbeat age > 2× configured interval |
| POST | /commands/{id}/result | credential or CONTROL token | ACK, unknown/wrong node 404 |
| GET | /status | `X-Grid-Token` | node/assignment snapshot; CONTROL only |
| POST | /ingest/minute, /ingest/event | per-node credential headers | node-authorized ingestion; verify in full integration |

`grid/config.py`: heartbeat interval defaults to **10 seconds**, coordinator URL defaults to `http://127.0.0.1:8765`, fleet shared token defaults to empty (admin auth denies when unset). Coordinator `nodes` and `assignments` are in-memory globals; DB-backed enrollment and command/ownership calls must be backed by a disposable PostgreSQL instance. No direct worker→PostgreSQL traffic is required by these routes.

## Isolated network matrix

| Source | Destination | Port | Required? | Boundary |
|---|---|---|---|---|
| Local coordinator process | 127.0.0.1 | TCP 8765 | yes for HTTP fixture | loopback only; no `0.0.0.0` |
| Local agent A/B/C | 127.0.0.1 | TCP 8765 | yes | outbound HTTP, per-agent enrollment credential |
| Coordinator | disposable PostgreSQL | isolated local TCP port | yes for DB-backed integration | loopback/private fixture only; port chosen by #240 |
| Agents | PostgreSQL | any | no | DENY |
| Any physical node/Tailscale/public interface | fixture | any | no | DENY; no LS5/PC4 access |
| SSH | fixture | 22 | no | not part of test |

Fixture ports are not a production prescription. Use separate temp dirs, random credentials, disposable DB, disabled external market/websocket connectors and **no real orders or physical network**. No real node IDs, real Tailscale IPs or secrets in fixture logs. Cross-check #239 trusted bootstrap input/output schema and #240 PostgreSQL connection/migration/cleanup requirements at their exact HEADs before running.

## Test sequence and expected evidence

1. Confirm coordinator and **actual existing agent** entrypoints and CLI/config from source; log exact tree SHA, Python version, dependency lock and chosen isolated ports.
2. Start disposable PostgreSQL; run supported migrations; coordinator bound explicitly to 127.0.0.1; agent A/B/C using distinct IDs and one-time enrollment tokens. Capture sanitized enrollment result without credentials.
3. Verify 3 independent credentials; wrong token, expired/reused enrollment token and credential for another node must fail. Verify whether CONTROL fallback is intentionally permitted on `/heartbeat`; **do not give agents CONTROL token**.
4. Heartbeat 3 nodes for ≥3 intervals (default 10 s), assert per-node identity and returned ownership/assignments; test timeout at >2 intervals and acceptance. Distinguish stale acceptance from coordinator's other 3×-heartbeat cutoffs.
5. Network fault injection only through in-process ASGI transport, loopback proxy or deterministic adapter: delayed/duplicate/drop/reorder heartbeat, 401/403, disconnect, coordinator restart and reconnect storm. Measure bounded retries/backoff, stale node handling and duplicate registration, without real external traffic.
6. Verify `runtime_state` not ACTIVE produces no live symbols; assignments cannot leak across nodes; ownership protocol is 1 and no duplicate lease is granted. Test task command ACK identity and replay with disposable DB.
7. Restart coordinator while keeping disposable DB; verify registration persistence vs in-memory `nodes` reset and required re-heartbeat; reject stale/forged credentials. Document whether restart loses assignments.
8. Capture per-case JUnit, monotonic timings, process exit codes, sanitized log and artifact SHA256. **Only actual completed cases can be PASS.**

## Security gates

**P0 candidate**: `node_auth` accepts a valid fleet CONTROL token as fallback even when node credential fails; CONTROL compromise can impersonate any node. Explicitly test invalid credential + CONTROL token behavior, then decide whether to remove fallback with a separate compatibility review. Do not silently change existing agent auth semantics.

**P1**: `/health` is unauthenticated; avoid leaking secrets in its response. `0.0.0.0:8765` exposes coordinator on all IPv4 interfaces absent firewall; use loopback only for this fixture. Remote production requires independently reviewed TLS termination, Windows Firewall and Tailscale ACL default deny, key-only SSH, certificate identity, and secret isolation. None are established by this fixture.

**BLOCKED evidence**: real agent startup and retries, actual disposable PostgreSQL migrations, #239/#240 integration, hosted CI/JUnit and production host controls remain unverified until executed.
