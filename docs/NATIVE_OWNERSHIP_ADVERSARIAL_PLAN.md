# Native adversarial audit plan

Base5d01b1277ebb4854f772aa48101f454fc0166202; PR195 comment6219305936.

Use TDD for acquisition exception safety, pre-existing resource scope, ACE/SID
bounds and cleanup ordering. Run only model/static tests locally. Native tests
require hosted Windows CI policy and the existing fresh GUID fixture factory.

Add actual fixture-only junction creation/attempts, pinned ancestor rename,
ACL/hardlink/concurrent namespace mutations, ACL ABA, abandoned mutex and cleanup
fault injection around real handles. Do not exhaust the runner handle table:
exercise a bounded fixture quota and explicitly report kernel exhaustion unproven.
Privileges preventing junction attacks produce BLOCKED_UNPROVEN JUnit skips,
not a synthetic readiness PASS. Preserve deterministic model reparse regressions.

All existing17 native tests and PS5.1/7 launchers remain mandatory. New adversarial
JUnit gate counts every testcase and exports tested/unproven outcomes. Reports
stay BLOCKED, schema2 remains off, no existing paths/prod/LS5/LS7/native local run,
SQL/initdb/services/port binds/deployment/merge. No production mutex/ACL changes.

Deliver audit documentation, regression reproducers, independent review and a
separate Draft PR with exact-HEAD Actions. Distinguish observed kernel invariants,
modeled failure paths and limitations (privileged ABA/same-process introspection).

Local evidence:86 focused model/lifetime/parser/evidence tests passed. Full offline:
1596 passed,80 skipped,7 subtests passed,4 existing FastAPI warnings. Real native
old/new suites were deliberately not run locally. PS5.1/7 each passed the10-case
model launcher. actionlint, compileall, PS5.1 parser and diff-check passed.
Independent review found and resolved ACL evidence false-positive and original
read-cause accounting; final targeted review found no remaining blocker. Actual
kernel outcomes and explicit unproven scenarios remain CI-pending.
