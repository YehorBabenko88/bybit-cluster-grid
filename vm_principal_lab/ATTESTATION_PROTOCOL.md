# VM principal isolation — offline attestation protocol

Issue #201 · Draft PR #204 · model-only. This document is **not** permission to run a VM.

## Evidence boundary

A configured/declared SID is not evidence of the observed user SID. A Windows token user SID is distinct from token group membership, elevation and integrity. ACL text is not an effective-access decision. An attestation made by the guest under test is not independent evidence. Each observation requires a source identifier, timestamp, target guest identity, immutable evidence digest and independently verifiable provenance. Absence or contradiction is **BLOCKED_UNPROVEN**, never PASS.

## Required independent evidence

1. Collect declared principal identity as a separate input, never as observed identity.
2. In an authorized future lab only, independently attest actual SID, token user SID, group SID attributes, elevation and integrity level.
3. Attest file/object ownership, DACL, deny/allow ACE order and effective read/write/WRITE_DAC access separately.
4. Require distinct security principals and sources per guest. Equal SID values or duplicated source provenance are blockers.
5. Treat local/host administrator interference, privilege escalation, unknown token state, missing provenance and mismatched digests as STOP or BLOCKED.
6. Review every negative case independently; a passing Python model test proves only classifier behavior, not a guest outcome.

## Twelve negative cases

| Case | Negative condition | Expected execution state |
|---|---|---|
| VM-NEG-01 | Declared SID only | NOT_RUN |
| VM-NEG-02 | Same actual SID across guests | NOT_RUN |
| VM-NEG-03 | Token user SID mismatch | NOT_RUN |
| VM-NEG-04 | Elevation unknown | NOT_RUN |
| VM-NEG-05 | Unexpected elevated token | NOT_RUN |
| VM-NEG-06 | Group SID evidence missing | NOT_RUN |
| VM-NEG-07 | Shared privileged group | NOT_RUN |
| VM-NEG-08 | Cross-guest ACL read | NOT_RUN |
| VM-NEG-09 | Cross-guest ACL write | NOT_RUN |
| VM-NEG-10 | Owner can rewrite DACL | NOT_RUN |
| VM-NEG-11 | No independent attestation | NOT_RUN |
| VM-NEG-12 | Hostile administrator | NOT_RUN |

## Invariants and scope

```text
status = BLOCKED_UNPROVEN
readiness_passed = false
execution_authorized = false
VM-NEG-01..12 = NOT_RUN
hostile-admin = STOP
```

No VM provisioning, Windows token interrogation, LS5/LS7 access, services, PostgreSQL, deployment or production mutation. The Python 3.11/3.12 workflow tests offline model invariants only. PS5.1/7 existing commissioning checks are not proof of this protocol's guest isolation. Draft PR must not be merged or reclassified as readiness based on green CI.
