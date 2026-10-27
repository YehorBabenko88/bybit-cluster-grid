# Independent Windows transport regression contract (2026-10-27)

Source under review: PR #244 checkpoint `2b978b7f46fdfe70b6bbd9bb14a32e34728e2eb5`.
This document is an independent QA contract, **not** a native PASS or a physical authorization.

## Original CI observations

Workflow run 40547110334: all four PowerShell 5.1/7 x Python 3.11/3.12 matrix jobs failed at both hosted AppContainer Python lifecycle and undebugged boundary checks. Mandatory gate failed. Build, read-only diagnostics, WFP model and restore steps succeeded. Primary receipt creation was skipped. Job 122340550714 explicitly reports UNDEBUGGED_BOUNDARY_BLOCKED. WFP root cause UNKNOWN.

## Required adversarial regressions (separate identities)

1. Ready host listener: independently assert bind/listen and accept readiness before child connect; verify child result, deadline and teardown. A timeout is FAIL, never PASS.
2. Bound but non-listening socket: expect refusal (WSA10061) and prove it is not conflated with listener timeout.
3. Force accept cancellation, backlog saturation and listener closure; assert bounded completion and distinct terminal status.
4. Wrong PID, wrong nonce, stale timestamp, duplicate nonce and cross-run replay must all reject even when other fields are valid.
5. Missing or malformed native receipt, unexpected skip, mismatched run/attempt/HEAD, duplicate JSON keys and duplicated JUnit identities must reject.
6. Execute identical cases in debug and undebug modes, PowerShell 5.1/7 and Python 3.11/3.12; report all differences, do not collapse outcomes.
7. Validate effective AppContainer token, package SID, capabilities, restricted SIDs, integrity and inherited handles using OS-native observation; never infer from launch flags.
8. WFP: only attribute causal filter with correlated event, matching PID/AppContainer identity, endpoints, timestamp and filter ID; absence of event remains UNKNOWN.

## IPC alternatives acceptance

- Broker: authenticated caller identity and capability-scoped request, no confused deputy, per-request replay fence, bounded queue and crash recovery.
- Named pipes: explicit protected DACL, client impersonation level verification, server identity, reject remote clients, no inherited privileged handles, reconnect replay protection.
- Restricted token/AppContainer: effective-token verification; network and filesystem denied except explicitly proven capabilities; no child escape.
- Job Object: kill-on-close, nested job behavior, breakaway prevention, memory/process/time limits, orphan cleanup.
- Tailscale: independent transport authentication is not authorization; bind authenticated application identity and request nonce to exact operation.

## Physical gate

Effective SID/ACL custody, PostgreSQL PGDATA/roles, executable/source identity, owner-authenticated authorization, durable anti-replay, reboot recovery, handle-bound cleanup and native containment must all be independently evidenced before G1. Physical SID/ACL 0/10 NOT_RUN; all 20 G1 phases BLOCKED/null argv; Execute/Cleanup NOT_AUTHORIZED; Deployment NO-GO. No LS5/PC4 operations.
