# Physical Public Smoke S0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow the owner's explicit no-commit/no-push instruction for this change.

**Goal:** Build a reviewable standalone LS5/PC4 public BTCUSDT smoke experiment with bounded execution and inert hosted packaging; do not start a physical run.

**Architecture:** A narrow Coordinator accepts authenticated Worker registration, heartbeats and one public-data assignment. The PC4 Worker subscribes only to the two fixed BTCUSDT public topics. A portable CPython package and explicit PowerShell dispatcher keep source/package custody and operator authorization separate from run logic.

**Tech Stack:** Windows CPython 3.12, Python standard library, aiohttp 3.14.5, cryptography 50.0.2, TLS peer certificates, Win32 custody/token inspection, PowerShell 5/7 compatible wrapper, hosted GitHub Actions.

**Spec:** `docs/PHYSICAL_SMOKE_S0.md` is the operator-facing scope and future run contract. Owner instructions and runtime closed schemas are authoritative; reconcile any discrepancy before approval.

## Global Constraints

- This is not production Grid, full Grid, HA or G1; all twenty G1 gates remain BLOCKED.
- No native/physical/network/package build or dependency installation locally; local checks use pure fixtures and source/AST inspection only.
- No commit, push, physical transfer, staging or execution under this implementation task.
- Independent review and complete human G0 must precede preparation and execution; standalone S0 authorization does not promote manifest authority flags.
- Required `hostnames` maps logical LS5/PC4 roles to independently observed exact uppercase Windows NetBIOS names; aliases are not normalized, and unknown values stay null/BLOCKED. Match role hostname and full operator SID.
- Exact Bybit URL `wss://stream.bybit.com/v5/public/linear`; symbol `BTCUSDT`; only subscribe/ping; fixed public order book and trade topics.
- Duration exactly 300 seconds with native owned-Job kernel lifetime limit and Python self-watchdog backstop; Worker uses remaining Coordinator window; at least 240 seconds actual healthy collection for `PUBLIC_SMOKE_OBSERVED`; early operator stop is PARTIAL.
- No DB, private/trade exchange access, service/account/firewall changes, foreign signals, PID kill or automatic cleanup.
- Fresh `GridS0-<UUID4>` root; immutable source/package pins; protected root with exactly SYSTEM, Administrators and approved operator explicit Full Control ACEs.
- Package bootstrap already has protected trusted parent/custody; never auto-expand into an unsafe existing location or rewrite existing ACLs.
- CA private key only in memory; role keys private and unlogged, excluded from evidence; future PC4 transfer requires separately authorized encrypted verified SSH.

## Review Focus

- Package/extracted divergence: a matching ZIP digest must never excuse altered extracted code or unsafe executable custody.
- Runtime/token changes: actual machine/SID, medium unelevated token, disabled administrator group and only ChangeNotify enabled must be checked, with failures closed.
- Ambiguous JSON and replay: duplicate keys, extra fields, timestamps, repeated conflicting IDs and wrong peer role cannot create assignment authority.
- Partial runs: disconnects, late Worker start, early stop and missing role evidence cannot satisfy healthy duration by wall-clock elapsed time.
- Bootstrap provenance: no executable may verify its own untrusted staging provenance; external owner staging and independent source review remain required.

## Task 1: closed policy and authenticated bounded protocol

**Files:** `s0_smoke/policy.py`, `s0_smoke/protocol.py`, `s0_smoke/wire.py`; tests `tests/test_s0_policy.py`, `tests/test_s0_protocol.py`.

**Interfaces:** `validate_plan(value, head)` accepts only the exact plan schema; `load_json(raw)` parses bounded object JSON without duplicate keys or nonfinite/float values; `outbound(op)` returns the fixed subscribe/ping payload; `import_allowed(name)` blocks production modules. Wire/protocol routines enforce role, sequence, timestamps, quotas, registration/heartbeat/assignment and peer authentication without production imports.

- [ ] Write failing pure tests for exact plan fields, integer-only 300, UUID4, source pin, literal distinct approved IPs, full distinct SIDs, exact actual per-role hostnames, approved port and fixed endpoint/topics.
- [ ] Add failing tests for private/trade URLs, inherited secrets/config, malformed/bounded JSON, production imports and unsupported outbound operations.
- [ ] Add protocol fixture tests for wrong role, replay/conflicting duplicate, bad timestamp, quotas and failed registration/heartbeat/assignment.
- [ ] Run targeted tests and observe the missing behavior before implementing the minimum closed policy/protocol.
- [ ] Run the policy/protocol tests again; require no skips and no real socket/network access.

## Task 2: native custody adapter, fresh storage and public PKI

**Files:** `s0_smoke/windows.py`, `s0_smoke/storage.py`; test `tests/test_s0_windows.py` and applicable runtime fixture tests.

**Interfaces:** Native calls are behind explicit runtime adapters, never import-time actions. Pure ACL/token/path parsers reject unsafe descriptors and identity states. Storage creates only fresh protected pair/role/temp objects and returns public inventory; no existing descriptor rewrite. Preparation on LS5 creates paired role configs/certificates/keys, with CA key held only in memory, and a local LS5 prepared marker. The PC4 transfer material has no marker. After separately approved verified encrypted SSH transfer of only the six role files, PC4 Prepare imports them from protected input into a fresh same-GUID local pair root and creates its own native-identity marker.

- [ ] Write failing binary fixture tests for exactly three trusted root ACEs, wrong rights/flags/principals, malformed ACL/SID, hardlink/reparse/path aliases, token elevation/admin and privilege failures.
- [ ] Add fixtures for unexpected actual host/SID, changed source/ACL, preexisting root, partial preparation and key exclusion from evidence.
- [ ] Implement minimum Win32 inspection and fresh protected creation behind the adapter, retaining pure parser tests locally.
- [ ] Verify pure tests only; reserve actual Win32 calls and physical custody inspection for future separately authorized G0/run phases.

## Task 3: CLI orchestration, bounded foreground roles and evidence

**Files:** `s0_smoke/entry.py`, `s0_smoke/cli.py`, role runtime/evidence modules under `s0_smoke/`; CLI/runtime fixture tests under `tests/`.

**Interfaces:** Entry mapped to `runtime/App/s0.py`. Flags: `--action plan|preflight|prepare|execute|status|stop|evidence`, `--root`, `--package-root`, `--package-zip`, `--config`, `--expected-head`, `--expected-package-sha`, and `--approved`. Approval is mandatory for prepare/execute/stop/evidence. Plan performs no subprocess or write. Each action validates closed inputs; mutation follows source/package/custody verification.

- [ ] Write failing synthetic dispatch tests showing missing pins/custody stay BLOCKED and prepare never starts transport.
- [ ] Test full ZIP digest plus extracted closure, exact source pins, package member restrictions and altered bootstrap/runtime files.
- [ ] Add injected-clock/transport tests for 300 second self watchdog, remaining Worker window, disconnect budget, own stop notification, and no foreign signals/PID kills.
- [ ] Test healthy interval ≥240, both role evidence required, early stop PARTIAL, corrupt/missing/hash-conflicting evidence and secret/key exclusion.
- [ ] Implement minimum explicit dispatch, role orchestration and evidence aggregation; verify synthetic tests without real Bybit or physical calls.

## Task 4: portable package, dispatcher and hosted job

**Files:** `tools/build_s0_package.py`, `installer/physical-smoke-s0.ps1`, `installer/physical-smoke-s0/S0Launcher.cs`, `tests/test_s0_package.py`, S0 hosted workflow under `.github/workflows/`, `s0_smoke/requirements.txt`.

**Interfaces:** The externally staged protected package root retains the exact original archive as `source.zip`, the sole extracted-closure exclusion. Builder command `python -m tools.build_s0_package`; emits `s0-package/physical-smoke-s0-windows-py312-<HEAD>.zip` plus `package-receipt.json`. Manifest schema 1/profile PHYSICAL_SMOKE_S0 pins every other file with SHA256/size, exact Git source blobs, head/tree/run/attempt/Python; authority flags all false. Wrapper maps the flags above and never downloads, extracts, installs or repairs.

- [ ] Write failing fixture tests for exact hosted guard, physical host denial, traversal/device/casefold member collisions, size bound, deterministic archive and byte mutation detection.
- [ ] Test dependency allowlist/active closure and regular-file constraints; retain Python/dependency licenses; exclude hooks, scripts, cache, production dependencies and private files.
- [ ] Implement portable runtime with python.exe, root DLLs/DLLs extension files, stdlib.zip, Site and App; both ._pth files have only stdlib.zip/DLLs/Site/App and no import site.
- [ ] Implement Plan-first wrapper, literal paths/pins, original-ZIP SHA check, original-manifest-pinned byte loading of the hosted native launcher, explicit approval and closed-environment foreground bundled console launch; native own-Job timeout is 300 seconds for Execute and 60 otherwise; parse PowerShell AST without executing a physical action.
- [ ] Add hosted-only Windows exact-checkout build job with reviewed C#5/.NET4.8 DLL compilation, source/DLL package pins, actual parent-primary/created-child token fact validation before resume, inert artifact upload and synthetic tests; receipt identifies actual executed HEAD/tree/run/attempt.
- [ ] Run targeted pure package tests; do not run the builder locally.

## Task 5: reconcile, review and stop before physical use

**Files:** `docs/PHYSICAL_SMOKE_S0.md`, this plan, affected tests/workflow.

- [ ] Reconcile documented flags, source.zip custody, config/root layout, local-role preparation markers, six-file PC4 transfer, private temp directories, manifest fields and new s0-evidence.zip export against final implementation. Prepared-role Preflight cannot inspect an absent root; pre-Prepare G0 remains separately reviewed manual read-only inspection.
- [ ] Run appropriate complete source/pure test inventory and AST checks; record failures explicitly, with no skipped/physical result masquerading as pass.
- [ ] Obtain independent review of source, bootstrap provenance, package limits, PKI/storage, role protocol and evidence duration logic; resolve actionable findings.
- [ ] Leave the owner a concrete reviewable implementation and explicit BLOCKED G0/physical status. Do not commit/push or proceed to staging/transfer/run.

The optional hosted `tools/probe_s0_public_ci.py` fixed-endpoint ten-second public diagnostic may report BLOCKED or OBSERVED_PUBLIC_NOT_PHYSICAL; it is not a gate or physical approval. No new PC4 connection or physical inspection is established by this plan.

Future physical phases are governed by the runbook's separate human gates, not by checked implementation boxes. A successful hosted package or synthetic test remains evidence only for its own scope.
