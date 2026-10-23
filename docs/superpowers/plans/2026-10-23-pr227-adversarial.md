# PR227 adversarial acceptance plan

Baseline: da69209af86567232fb3038a899580fe2e061a0b. Work only in
audit/pr227-adversarial-20261023; never modify the dependency branches.

1. Reproduce extra runtime privileges, rewrite-rule drift, metadata issuer/ACL
   gaps and checkout receipt substitution. SQL runs only after the existing
   GitHub-hosted disposable PG18 provider attestation, never locally.
2. Add minimal fail-closed checks and passing regressions. Preserve preparation
   transaction/advisory lock, schema-48 validation and legacy rollback.
3. Run the same SQL probes against an exported exact baseline and the candidate,
   with separate JUnit and explicit baseline-vulnerability labels.
4. Independently inspect original exact-head artifacts; test the candidate on
   Windows/Linux, Python 3.11/3.12 and PowerShell 5.1/7. Publish a separate Draft PR.
5. Report limits: trusted owner/admin can change authority after verification;
   startup verification does not authorize persisted ACTIVE, market collection,
   trading or physical execution. Physical SID/ACL remains 0/10 NOT_RUN.
