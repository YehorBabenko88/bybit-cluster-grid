# LS5 ACL remediation plan

Base: PR236 a7e695d8a937a19e28cebe48668f9927cf2fd9b1. Own branch only.
Audit main and historical active source too; do not modify other PRs or hosts.

1. Record installer/launcher/promotion/task/ACL call sites with exact lines and
   distinguish source defects from unobserved LS5 installation history.
2. Test a pure strict snapshot/ACL plan contract: SID-only roles, executable vs
   secret vs mutable-data policy, complete inventory/ancestor custody, reparse,
   hardlink, hashes, disabled tasks, runtime uncertainty and role uncertainty.
3. Test a non-authorizing ACL transaction/recovery model with original SDDL and
   object identities. Preserve snapshots; block stale/replayed journals and
   concurrent identity/ACL changes. No automatic insecure rollback or activation.
4. Make unsafe legacy bootstrap/protect entry points fail before effects pending
   a reviewed protected-staging executor; never duplicate Runtime Guard/mutex.
5. Add hosted GUID-only Windows structural ACL/link/idempotence/rollback tests,
   pure PS5.1/7 contracts, strict JUnit/JSONL/head/hash CI evidence, no real users.
6. Publish own Draft PR with actual terminal CI and exact artifact hashes, ACL
   before/after matrix and operator-only preflight/STOP/recovery design.

Physical PC4 0/10 NOT_RUN; Execute/Cleanup NOT_AUTHORIZED; Deployment NO-GO.
