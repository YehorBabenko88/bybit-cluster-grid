# Native ownership feasibility / lifetime prototype plan

Base8bb58f56cf42c87a0325c7b00d1c5fc8eaaa63b8; task PR194 comment6218595348.

Design: a Python in-process session engine with a mocked object/handle backend
and a ctypes Win32 backend restricted to a freshly created GUID fixture on hosted
Windows CI. No caller path, GridLab target, schema2 integration or executor.
Both outcomes remain status BLOCKED; passing fixtures are SYNTHETIC_ONLY.

The same handles and two fixture-only mutexes remain held across verification,
callback and post-consumption checks. A borrowed read view invalidates on return,
closure, re-entry or error. Compare initial identities, link/type, ACL and exact
bytes, current path identities and tree membership at read/consumer boundaries.
Native backend has no Add-Type/compiler/child process; PS5.1/7 launch the explicit
Python fixture test runner, not a runtime adapter. Local runs use mocks only.

Steps:
- [ ] Write failing lifetime/TOCTOU tests; implement bounded model and session.
- [ ] Add explicit Win32 bindings and hosted-CI-only fresh fixture factory; no
  existing path accepted and no fallback if ACL/native APIs unsupported.
- [ ] Negative and positive mock tests; native sharing/identity/ACL/lifetime tests
  on disposable hosted fixtures only. No local native execution.
- [ ] Extend Python3.11/3.12 and PS5.1/7 CI, preserve previous gates; full offline
  tests, static checks, independent code review and exact-SHA Actions.
- [ ] Document assurance limits, race windows, lifecycle/disposal, remaining
  blockers, changes and run IDs in a separate Draft PR.

Policy: environment markers restrict fixture execution; they are not machine
attestation. Safety also relies on factory-only new GUID path, no adoption or
external root input, no cleanup, no production API and immutable BLOCKED flags.
ACL setup changes only objects newly created by that factory in disposable CI.
No trusted/untrusted Python callback sandbox is claimed; callbacks/hooks are test
code. Privileged adversaries and atomic namespace/ACL isolation remain blockers.

Local evidence:75 model/lifecycle/parser/policy tests passed; full offline1585
passed/63 skipped/7 subtests,4 existing FastAPI warnings. All17 native tests were
intentionally NOT run locally. PS5.1/7 each ran the10-case model driver. Actionlint,
compileall, PS5.1 parser and diff-check passed. Independent review defects for
probe cleanup, mutex registry and two-mutex ordering were reproduced and fixed;
unknown/secret-shaped exception codes are sanitized. Final review found no
remaining actionable issues in the scoped prototype. Native evidence pending CI.
