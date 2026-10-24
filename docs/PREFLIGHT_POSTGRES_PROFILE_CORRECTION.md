# Preflight PostgreSQL profile correction

The generic preflight uses PostgreSQL 16. Its recursive pytest collection previously
also executed seven PostgreSQL 18-only transaction/restore cases, failing before
those cases opened a database connection. The dedicated PG18 workflow was excluded
on the integration branch, so a green core first-boot gate did not close this gap.

The PG16 unit step now excludes only the two PG18-specific files. The same workflow
calls the reusable GitHub-hosted PG18 workflow, which executes those exact seven
cases and rejects incomplete or failed JUnit. `required-preflight` runs even when
a dependency fails and accepts only SUCCESS from both profiles. SKIPPED and
CANCELLED are not accepted. Existing test assertions are unchanged.

This correction does not turn the seven older probes into the stronger container-
attested first-boot provider. They retain their fixed, disposable hosted-service
profile. Their proof scope is transaction/restore behavior in that service; the
independent 32-case attested PG18 gate and 26-stage real E2E remain necessary.
No claim about PC4, LS5, physical authorization, HA or production follows.

Verification: the two new workflow-contract tests failed before the correction
(missing companion job and workflow_call), then passed. Actual hosted results must
be read at the new exact commit; older successful runs are not evidence for it.

Physical PC4 0/10 NOT_RUN. Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO.
