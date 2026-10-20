# Isolated offline RC publication gate

Review branch: `review/offline-rc-20261020`, based on verified local RC
`6d1b64de05c4b6f29b12153c4da4b20fcb28bce3` and shared review base
`audit/codex-vm-test-attestation-20261016` at
`5d18b2810a8b1b22ce59e46334d35e07f55c46c7`. Source PR204/205/206/207/209
heads remain those in `independent_audit/composition.json`; no source PR modified.

All inherited jobs are excluded specifically for this review head/ref, at job
level before runner/service provisioning. This leaves their behavior unchanged
on other branches. Only `offline-rc-review` runs code/test/static jobs on hosted
Windows3.11/3.12 and an Ubuntu actionlint job. There are no services, SQL,
PostgreSQL/initdb, VM, installer, deployment or physical operations in this CI.
Inherited skipped jobs are NOT evidence of completed integration checks.

The aggregate workflow checks out the exact PR HEAD (manual:github.sha),
with core.autocrlf=false for exact pinned source bytes. It requires pytest9.1.1,
isolated hash-pinned cryptography50.0.2/cffi/pycparser wheels, pip check,
PowerShell5.1/7 syntax and public-test-key/model-only smoke.

The aggregate test inventory is unchanged:35 files,739 test nodes,78 successful
subtest reports, all10 former P2 regressions. Publication-gate validation tests
are a separate invocation and do not inflate739. Live pytest event receipts
check all739 call identities,78 subtest reports and absence of any skipped,
xfail, failed or errored report. JUnit independently reconciles739 named rows
and817 suite.tests (739+78). The old report's wording817 'entries' meant this
suite total, not817 separate testcase rows.

The legacy RC inventory replaced every backslash, including escaped parameter
text such as \\n, with /. Publication uses raw pytest IDs, normalizing only
the path before ::. The739 raw IDs reconcile bijectively with the unchanged
legacy inventory; ten regression IDs are mapped through the same checked
bijection. Neither parameter values nor rejection assertions were weakened.

Shared205/206 file SHA256 checks are exact constants in publication_gate.py:
ff492592757a277661e60d554f73ebbb11b04b7e1f7bee9f0757562ac68392fd and
dc76589fe660509c53ecefc957019b8f2448c42bb0ff429ebb1701b4f8dc8192.

Artifacts bind the actual checked-out head SHA, raw event receipt and exact
JUnit IDs. They are CI metadata, not signatures or physical authorization.
All outputs retain execution_authorized=false, readiness_passed=false,
physical_ready=false, schema2_enabled=false,12 real guest cases NOT_RUN.
Physical deployment remains NO-GO: native identity/ACL/PGDATA ownership,
trusted time, protected authorities and durable nonrollback protection are
unproved. Correlated replay checkpoint+anchor rollback remains a model limit.
No merge is authorized and main is not changed by publication.
