# LS5 native ACL custody executor — security contract (design stage)

Status: DESIGN_ONLY / NOT IMPLEMENTED. Based on PR #237 exact HEAD `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`.

## Authority boundary

This document is not authorization to inspect, alter, repair, or start LS5/PC4. Physical SID/ACL PC4: 0/10 NOT_RUN. Execute NOT_AUTHORIZED; Cleanup NOT_AUTHORIZED; Deployment NO-GO. No existing `-Apply` refusal may be relaxed by a design-only change.

## Native executor requirements (all mandatory before enabling Apply)

1. **Trusted bootstrap:** executable, native libraries, interpreter, manifests and evidence store must originate outside the currently Users-writable Grid roots. Verify publisher/source and complete hash closure before loading any Grid code. A matching old launcher hash alone is insufficient.
2. **Stable handles:** open the volume and every path component with reparse-point traversal prohibited. Use Windows native handle APIs and request only necessary access; validate volume serial and file ID, reparse tag, file type and hardlink count. Re-check the same handles before and after each descriptor change. Reject any unknown object, junction, symlink, mount point, hardlink alias or changed identity.
3. **Ancestor and replacement custody:** prove parent `DELETE_CHILD`, child `DELETE`, `WRITE_DAC`, `WRITE_OWNER`, inherited ACEs and effective token rights for all relevant untrusted principals. Merely verifying that a leaf file has Users RX is insufficient. Account for already-open writable handles, concurrent renames and directory replacement. If exclusivity cannot be established, STOP; never rely on path-based re-lookup as proof.
4. **Full closure:** include both Grid roots, every installed release (currently six), bootstrap/staging/previous trees, all launchers, version pointers, `.env`, Python base and venv, `pyvenv.cfg`, `.pth`, `sitecustomize`, `site-packages`, native DLL resolution, import sources, updater/recovery tools, manifests, logs, spool, backups and data-writer boundaries. Unknown or unclassified path means BLOCKED.
5. **Quiescence and ownership:** independently enumerate scheduled task XML/actions/principals, processes and complete command lines, services, writers, handles and task ownership. `PowerGridForecastTask` and `grid_pg_test` remain unrelated/unknown until proven. Hold existing release mutex and enforce a separately proven exclusion against competing installer, updater and runtime writers for the entire transaction. No automatic process termination.
6. **Protected journal:** prior to any DACL mutation, durably write an append-only, authenticated journal to an independently protected location. Bind run ID, exact source HEAD, approved scope, volume/file IDs, original owner/group/DACL/SACL where authorized, original hash, intended descriptor, ordered operation and pre/post handle receipts. Flush journal before mutation; reject replay, truncation, forged receipts, stale handles, or contradictory state.
7. **Transactional mutation:** only a separately reviewed native Windows implementation may set descriptors on already-verified handles. Do not use recursive `icacls /reset`, ownership takeover, localized group names, or modifications to system ancestors. Preserve approved service rights and WAL/data. Verify each post-state through the original handle and an independent observer. On partial failure, STOP and preserve evidence.
8. **Recovery:** do not automatically restore an insecure Users-write DACL or Users-readable secrets. Reacquire and verify the exact same object identity, current descriptor and journal chain before any individually approved restoration. Never restore to a replacement object. Missing proof => manual recovery / BLOCKED.
9. **Trusted rebuild:** tightening ACLs does not establish that existing code, modules, DLLs or secrets are uncompromised. Reconstruct executable closure from trusted artifacts under a newly protected root; assess credential revocation/rotation separately. No activation from old release solely on ACL PASS.
10. **Authorization separation:** design/test approval is not physical maintenance authorization. Independent physical verification and separate activation approval remain mandatory.

## Required offline negative tests

- Directory-only inherited Users `FILE_ADD_FILE` / `FILE_ADD_SUBDIRECTORY` while leaves are RX.
- Parent `DELETE_CHILD` or child `DELETE` permitting replacement; `WRITE_DAC` and `WRITE_OWNER` via group/token.
- Junction/symlink/mount-point swap before open, between verification and write, and after write.
- Hardlink alias, changed file ID, volume ID or reparse tag; ADS and path aliases.
- Existing untrusted writable handle and concurrent writer; unknown task/action/command line.
- Incomplete Python import/DLL closure and malicious `.pth` / `sitecustomize`.
- Forged/duplicated/truncated journal; mismatched HEAD, run ID, source hash, SDDL/ACE, object identity, post-state.
- Crash at every journal boundary and every per-object mutation; replay and partial-rollback attempts.
- Denied access, malformed security descriptor, privilege absent, unsupported Windows API.
- Existing unsafe original ACL must never produce automatic rollback or activation.
- Unrelated Windows paths, PostgreSQL data/WAL, accounts and tasks must remain unchanged.

## Acceptance gates

| Gate | Expected status today |
| --- | --- |
| Offline snapshot model from PR #237 | PASS within synthetic scope |
| Native handle-based custody | NOT_IMPLEMENTED / BLOCKED |
| Durable authenticated journal | NOT_IMPLEMENTED / BLOCKED |
| Crash-safe native Apply and recovery | NOT_IMPLEMENTED / BLOCKED |
| Independent non-admin-token tests | NOT_RUN |
| Physical LS5 repair | NOT_AUTHORIZED |
| Physical PC4 SID/ACL tests | 0/10 NOT_RUN |
| Deployment / coordinator activation | NO-GO |

No implementation should report PASS for a native gate unless real Windows API calls and negative tests provide verifiable evidence.