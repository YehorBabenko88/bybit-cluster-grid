# Ownership verifier architecture and safe-part implementation plan

Base: 9a7b0735f0ea265854abbf3bfc6cc3c7b897ddf3. Scope: PR193 comment6201691580.

Decision: implement a pure, in-memory byte-contract diagnostic, not a native
ownership verifier. Keep schema2 rejected. Existing ownership APIs cannot retain
an authenticated file/directory handle session across consumer use. A positive
byte comparison must therefore still return BLOCKED, never a PGDATA capability.

Implementation sequence:
- [x] Reproduce missing byte-contract diagnostic with strict committed-journal,
  plan/hash/intent and exact tree tests, including byte-level corruption.
- [x] Implement bounded canonical comparisons reusing New-GridLabPlan,
  Get-GridLabFiles and Get-GridLabRecord. No filesystem/native/host providers.
- [x] Test both PS engines and Python3.11/3.12 CI. Assert all outcomes remain
  BLOCKED and no callbacks/native providers are invoked or hidden behind flags.
- [x] Document native P/Invoke, mutex, handle lifetime, identity/ACL/ancestor
  checks and consumption interface needed for positive ownership proof.
- [x] Run existing offline/PS tests, static checks, independent review, Draft PR
  and exact-SHA Actions gates; record the resulting run IDs and conclusions in
  the Draft PR body. Report blocked ownership separately from passed tests.

Review focus: cast/coercion and JSON ordering; BOM/CRLF/duplicate records; directory
case/type/duplication and unexpected contents; oversized inputs; forged native
or freshness assertions. No initdb, SQL, services, port binds or physical probes.

No changes to preparation/retirement mutators or Add-Type journal implementation.
Do not tighten retirement into COMMITTED-only: interrupted preparations need the
existing preserve-only retirement path. No cleanup or automatic ACL repair.

Review ledger: nested executable intent getters/coercion methods were reproduced
calling code before rejection, then rejected by strict shape validation before
serialization. Independent review reran all60 cases on both engines, found no
remaining actionable defects. Native positive proof remains unfinished. External
Actions execution results are recorded in the PR body, not implied by this plan.
