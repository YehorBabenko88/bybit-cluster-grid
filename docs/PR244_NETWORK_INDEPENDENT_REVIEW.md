# Independent PR244 network audit — 2026-10-24

Compared own PR241 with PR244 exact HEAD `38e6ab40928cbdd6a2d6d84cbb05b4628167258f` through GitHub source review. **No real E2E run or local pytest performed.** PR244 has its own composed source tree and harness; do not import its source-only tests into PR241, which lacks `integration/first_boot.py`.

## Verified by source inspection

- `integration/first_boot.py` uses **real `OwnedChild` Worker processes**, two names `synthetic-a`/`synthetic-b`, real enrollment over HTTP, coordinator health, concurrent enrollment, replay rejection, distinct credentials, real worker status, exclusive assignments, ingest duplicate/replay, worker crash/restart, coordinator crash/recovery and disposable PostgreSQL restart.
- Coordinator HTTP endpoint is allocated on `127.0.0.1` ephemeral port; `SyntheticFeed.start()` uses `web.TCPSite(...,'127.0.0.1',0)`. Child env overrides `COORDINATOR_URL`, REST/WS feed URLs, sets `COORDINATOR_CANDIDATES='[]'`, and strips production tokens/proxies/PG defaults. `require_ci()` gates Linux hosted pg18 job. Python audit hook rejects non-loopback sockets and DNS. **Not a kernel sandbox**; native extensions, child-process launch environment and container networking need independent scrutiny.
- `/enroll`, `/heartbeat`, `/nodes/{node_id}/acceptance`, `/status` and ingestion endpoints exist in `grid/coordinator.py`. Shared CONTROL token fallback in `node_auth` is a candidate authorization-boundary risk. No change to coordinator or Worker runtime in PR241.

## Network fault coverage versus request

| Scenario | PR244 source coverage | Independent verdict |
|---|---|---|
| Two real Workers + concurrent registration | explicit | Designed, not executed |
| Enrollment token replay | explicit HTTP 401 assertion | Designed, not executed |
| Exclusive instrument assignment | `assigned()` uniqueness | Designed, not executed |
| Duplicate minute delivery + changed payload | HTTP 200/400 assertions | Designed, not executed |
| Worker crash/restart | explicit process stop/start | Designed, not executed |
| Coordinator restart | explicit process stop/start | Designed, not executed |
| PostgreSQL restart | container pg_ctl restart | Designed, not executed |
| Wrong ingestion credential | HTTP 403 assertion | Designed, not executed |
| Network loss/delay/reordering/reconnect storm | no explicit fault injection found in inspected `first_boot.py` | **Coverage gap** |
| Spoofed node credential + CONTROL fallback | no explicit heartbeat cross-node negative case found | **Coverage gap** |
| Duplicate heartbeat and stale acceptance >2× heartbeat | no explicit direct assertions found | **Coverage gap** |
| Unauthorized external listener in native child | loopback policy guard; no external interface inventory evidence | **Evidence gap** |

## Codex handoff — additions for PR244, not a merge request

1. Add negative HTTP tests using real running Worker identities: credential A on node B heartbeat and acceptance must reject; invalid credential must reject; explicitly test whether shared CONTROL token fallback can impersonate a node (record as a contract decision, do not silently relax auth).
2. Pause one Worker network path in an **owned loopback proxy** without touching real network; assert node B remains active, node A becomes stale after >2 heartbeat intervals, reconnect recovers within bounded time and credentials/ownership are unchanged. Use deterministic delay/drop/duplicate/reorder/reconnect-storm faults with bounded resources and no production endpoints.
3. Test same enrollment token concurrent reuse: exactly one succeeds, the other returns 401; ensure no duplicate node registration/credential overwrite.
4. On coordinator restart assert in-memory `nodes` cleared, fresh authenticated heartbeat repopulates both; instrument assignment/ownership and command ACKs remain consistent with DB and fail closed until reconciled.
5. Record per-case JUnit, JSONL, actual child PID, HTTP status, monotonic timings, exact SHA, run/attempt and immutable artifacts. Distinguish static policy assertions from real foreground Worker execution.

**Gates:** Hosted run `40081972021` and exact-HEAD artifact verification required. PR244 local 769 tests +138 subtests are author-reported offline-only, not independent E2E evidence. PR241 branch is isolated; no deployment, merge or physical contact.
