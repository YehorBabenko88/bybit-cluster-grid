# GRID physical maintenance implementation plan

**Goal:** Deliver read-only residual inventory, independently checkable evidence and a hosted PS5 handoff reproducer, never physical authorization.
**Baseline:** PR244 exact 7aed9c1cedb567fd7df82d9e449a54c5cc31b2c4; do not edit its branch.
**Architecture:** PS5.1 local collector with injectable providers only in internal tests; pure Python strict offline consumer; blocked stage dispatcher; existing S0 independent verifier reused for Core20/Runtime2/package evidence.
**Constraints:** No physical calls during development, no DB connections/SQL, no changes to existing objects, diagnostic task preserved; every missing/unknown gate BLOCKED. Operator-supplied pins and assertion flags are not authenticated authorization.

- [x] RED: contract, duplicate/NaN/type/replay/digest/JUnit and mutation rejection tests.
- [x] Implement local metadata collector with redaction, exact fixed paths and no removal API.
- [x] Implement independent bounded snapshot/CI verifier and authorization-request plan.
- [x] Isolate hosted reproducer: source custody, native handoff, child create/execute, deadline/exit; ordinary mandatory native gates unchanged.
- [ ] PS5.1/7 mocked integration and native hosted-only tests; Python3.11/3.12 Linux/Windows, strict JUnit/source SHA receipts.
- [ ] Operator runbook, independent checklist, draft PR, exact-head CI evidence.

Physical execution, installer mutation executor, owner signature trust anchor, DB catalog confirmation and local Medium token acceptance remain BLOCKED. Implementation of a safe inventory is not an execution permission.

Local evidence:127 Python cases,19 mocked PS cases per PS5.1/7; hosted native and original artifacts pending. Independent code review found and fixed unstable UUID inventory, artifact layout and missing aggregate consumer; mocked JSON semantic validation also added. This is not designated physical acceptance.
