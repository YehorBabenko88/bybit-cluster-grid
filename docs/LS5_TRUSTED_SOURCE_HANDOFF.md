# LS5 trusted-source → native custody handoff (proposal v1)

Scope: offline interface contract only, **not** a provisioning tool, native observer implementation, or authorization token. This document is independently authored in PR #239 for integration review with PR #238. No cross-branch implementation is assumed.

## Immutable input envelope

An external, independently authenticated trusted-source provider must produce a canonical UTF-8 JSON envelope with:
- `schema=grid-ls5-source-handoff-1`; exact `source_commit` (40 lowercase hex); `release_id`; `manifest_sha256`; `content_tree_sha256`; `source_identity`; `signature_scheme`; `signature_reference`; `nonce`; `created_at_utc`.
- `files`: complete sorted path list with canonical Windows absolute path, content SHA256, file type, size, expected owner SID, expected DACL/SACL policy identifier, and explicitly classified load role (launcher, interpreter, config, import, extension, DLL, executable, auxiliary).
- `directories`: every ancestor and every loader search directory, with expected owner SID, custody policy, reparse status, inheritance expectation and executable/writable classification.
- `runtime`: exact Python interpreter, base runtime, pyvenv.cfg, site-packages directories, `.pth`, sitecustomize, Python import roots, DLL directories, working directory, environment allowlist and process token/privilege policy.
- `tasks`: exact scheduled-task XML hash, principals, actions, working directories, recovery and disabled-state expectations; unrelated tasks are separately classified.
- `provenance`: independently authenticated acquisition channel, source verification evidence and sealed staging handoff. Self-reported booleans are not proof.

The **native observer** must independently measure the filesystem object identity, handles, reparse points, hardlink counts, owner SID, DACL/SACL, ancestor chain, directory custody and task/service state. Its evidence must bind to the *same exact manifest hash and nonce*, reject mismatches and unknown fields, and return BLOCKED on missing or contradictory observations. Do not accept a path string, policy SHA or user-supplied `trusted=true` as identity proof.

## Cross-boundary validation

1. A source custodian authenticates provenance independently of the candidate runtime and computes the immutable manifest digest.
2. A separate staging principal places the bytes in a non-executable quarantine; the observer must not load any staged executable.
3. Native custody verifies object identity, access control and no pre-existing writers, and re-checks after any authorized transition to protected storage.
4. A separate independent verifier compares manifest, native observation and exact source commit. Every unresolved import, DLL load order, `.pth` execution, PowerShell module lookup, PATH entry or dynamic plugin is BLOCKED.
5. G0/G1 review may approve **only evidence compatibility**, never execute, cleanup, release switching or deployment. Physical G2–G6 require distinct authorization.

## Fail-closed rules

- Missing, skipped, incomplete, duplicate, inconsistent, unsigned/untrusted, expired or mismatched receipts: BLOCKED.
- Same-source self-attestation cannot establish independent provenance.
- TOCTOU or native handle uncertainty: BLOCKED.
- Synthetic CI PASS means only offline code/tests passed; physical `0/10 NOT_RUN`.
- No automatic promotion from `OFFLINE_MODEL_PASS` to `host_verified` or `execute_authorized`.

## Outstanding security work

**P0:** real LS5 trust-root ACL/SID and transitive executable dependency closure; independently verified source acquisition; native handle custody; task/recovery unknowns. **P1:** actual PowerShell module/DLL lookup and dynamic Python imports; cross-PR exact-head artifact compatibility and journal rollback validation. **P2:** pin hosted actions/dependencies, improve privacy-minimized evidence and long-term receipt archival.

This is a proposed contract for PR #238 maintainers to review, not a claim that PR #238 implements it.
