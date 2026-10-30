# Independent maintenance audit checklist

This is a technical checklist, NOT a human review, physical observation or grant.
Two independent reviewers/owner approval are still outstanding.

- [ ] Obtain exact HEAD and tree from GitHub/Git, separately from artifacts.
- [ ] Obtain original ZIP digests, run ID and attempt from GitHub API; recompute hashes.
- [ ] Compare every source pin to Git object bytes, not the mutable checkout.
- [ ] Verify all four original native cells and aggregate terminal SUCCESS; no skipped cell.
- [ ] Independently validate both raw Core20 and Runtime2, same fixture UUID,
      HEAD/package/run/attempt and the v7 combined receipt. Diagnostic output is not a receipt.
- [ ] Independently validate Windows/Linux Python3.11/3.12 JUnit + JSONL against
      frozen inventory; no duplicate, missing, skipped, xfail, error or failure.
- [ ] Check mocked PS19 named-case JUnit separately; do not label it native host observation.
- [ ] Check evidence SHA256 against original files; tampering with results/run/attempt
      or source pins must be rejected even if internal manifests are recomputed.
- [ ] Check command AST for any mutation, subprocess, network/SQL or remote execution
      in the collector. The separate hosted reproducer is not a physical tool.
- [ ] Verify PC4 GridS0-G0-TokenObserver is PRESERVE and matching names never imply ownership.
- [ ] Confirm no production env/secrets or raw command lines/usernames enter evidence.
- [ ] Verify AccessDenied/unavailable inventory != absent object, and reparse ancestry stops traversal.
- [ ] Treat owner-reported deleted directories/DBs as claims pending fresh observations.
- [ ] Keep PG metadata/catalog, effective firewall and local-session/token gates BLOCKED
      until independent authorized observations exist. High SSH IL is not local Medium.
- [ ] Ensure all mutating argv null and every G1 phase BLOCKED; approve no Stage,
      Prepare, Execute, Cleanup, DROP, firewall Apply, task/service/ACL/account change.

Expected verdict now: **BLOCKED / Physical S0 NO-GO / Deployment NO-GO**.
