# Stage 39.12 — Protected Staging Offline Preflight

Baseline: Draft #224, `2a93efaab1ec61cc5e2a872b95e47a0a8a227f55`.
Design input: [protected staging design](PC4_LSA_PROTECTED_STAGING_DESIGN.md).
Scope: pure, synthetic JSON modelling only. No staging has been provisioned or
examined. **Physical 0/10 NOT_RUN. Execute NOT_AUTHORIZED.** CollectLocal remains
NOT_AUTHORIZED. L1/L2 and physical deployment remain NO-GO.

## Contract and interpretation

`installer.protected_staging.validate(snapshot_raw, policy_raw)` accepts two bounded
JSON strings. It neither reads files nor queries identities, Windows, volumes,
LSA, ACLs, processes or networks. The independent policy supplies expected full
canonical SIDs, roots, run UUID, source commit, file inventory, toolchain hashes
and volume identity. The snapshot supplies synthetic observations. Duplicate
keys, type confusion, unknown fields and ambiguous lexical paths are rejected.
The existing bounded JSON parser is reused without changes.

Formal input schema: [protected-staging.schema.json](protected-staging.schema.json),
Draft 2020-12, closed objects. `$defs.result` describes the output. Structural
schema validation and semantic validation are separate: JSON Schema alone cannot
prove owner/SID relationships, full ancestor coverage or content equality. The
offline fixture is an invented example with synthetic identities and digests,
**not an inventory, authorization or model of an observed LS5 configuration**.

`OFFLINE_MODEL_PASS` means the supplied statements satisfy this model under the
supplied policy. It does not authenticate either input, their provenance, the
operator, observation time, compiler or machine. If both documents are forged
consistently, a model PASS is possible; it still yields `HOST_VERIFIED=false`.
Digests bind exact JSON input bytes for comparison, not their truth or freshness.
No report is signed and there is no replay/anti-rollback mechanism.

For every S1–S7, output contains separate `model` (PASS/FAIL/BLOCKED) and `host`
(always BLOCKED). Aggregate order is FAIL > BLOCKED > OFFLINE_MODEL_PASS. Unknown
supported observations (`null`) block their gate; invalid structure/policy fails
the whole contract. Early unknown within one gate can suppress later checks in
that gate, but never authorizes it. No output is an execution capability:
`HOST_VERIFIED=false`, `execution_authorized=false`, zero physical passes and
`physical_tests="0/10 NOT_RUN"` are invariant. JSON input cannot raise them.

## Evidence matrix S1–S7

The design did not assign S-numbered gates; this document defines that mapping.

| Gate | Synthetic PASS requirements | Future independent host evidence (currently BLOCKED) |
|---|---|---|
| S1 Identity / authorization scope | Exact trusted operator SID distinct from untrusted editors; modelled elevated token and approved admin group; SYNTHETIC_MODEL_ONLY with false host/execute flags | Owner-reviewed identity separation; independently observed SID, full token/group/privilege facts, operator approval scoped to a specific future operation |
| S2 Volume / custody / ACL / paths | Pinned FIXED volume; exact complete directory ancestors, source/toolchain files, fresh roots; no reparse; protected explicit DACLs and approved owners | Actual volume identity/type, owner and full security descriptors for every ancestor and input; group/effective access evaluation; custody preserved throughout use |
| S3 Source integrity | Commit and complete expected inventory equal before/at-use/after digests; modelled continuous custody | Independently pinned reviewed commit/blob/SHA256 manifest outside writable locations, all executed inputs and dependencies, evidence of continuous protection against replacement |
| S4 TEMP/TMP | Both canonical paths equal fresh empty private UUID workspace; shared=false | Actual process environment and compiler workspace, protected parents, no pre-existing contents or cross-user write access |
| S5 Toolchain / search | Exact resolved executable/dependency hash map; trusted search/current directory, no profiles, Windows PowerShell 5.1 x64 | Actual resolved compiler, runtime/modules/dependencies and provenance; trusted resolution chain; no PATH/current-directory/profile substitution |
| S6 Evidence | Separate non-overlapping fresh UUID workspace, no overwrite, exclusive creation, outside TEMP | Independent custody, actual exclusive creation and object ownership, protected manifest/log destination; compromise of runner cannot authenticate its own evidence |
| S7 Lifecycle | No reuse, unknown contents or cleanup authorization | Separate cleanup authorization and owned-file inventory, partial failure preservation, independent stop/recovery decision; no automatic deletion |

### Conservative ACL and path profile

Only SYSTEM (`S-1-5-18`), Administrators (`S-1-5-32-544`) and the exact trusted
operator may appear. These two built-in authority entries are deliberate trusted
exceptions to rejecting unrelated group ACEs. Exactly three explicit ALLOW ACEs
are required: SYSTEM/Admin FullControl `0x1f01ff`, operator ReadAndExecute
`0x1200a9` for source, toolchain and ancestors; operator Modify `0x1301bf` only
inside private TEMP/evidence roots. No inherited entries, unexpected deny/allow
entries, generic masks or additional privileges are accepted. An ordinary
source editor cannot own Source; writable private roots may be operator-owned.

This is deliberately stricter than the design's possible inheritance *within*
approved trees. It is not a complete Windows AccessCheck/SDDL evaluator and does
not model callback/conditional/object ACEs, mandatory labels, share ACLs, alternate
streams, hard links, privileges or dynamic groups. Host classification is blocked
because these are unresolved. Protected DACL booleans and continuous-custody claims
are assumptions, not measurements. The model may reject legitimate Windows root
ACLs; **do not retrofit C:\\ or other existing ancestors to satisfy this fixture**.
A future compatible topology/profile requires review and separate authorization.

Paths are canonical bounded ASCII absolute drive paths; drive-relative, UNC/device,
ADS, traversal, slash aliases, reserved DOS names, trailing dots/spaces and
case-colliding mappings are rejected. Only one pinned volume is modelled. Lexical
checks cannot resolve real mount points, aliases, reparse traversal or file
identities. Source, TEMP, evidence and toolchain locations cannot overlap. The
declared input inventory is authoritative only for the synthetic policy: completeness
of real runtime/module/compiler dependencies still needs independent review.

## Tests and hosted CI

New tests have their own committed node/JUnit inventory and `staging-offline.xml`.
The inherited 575-case scope has a separate inventory and `staging-baseline.xml`.
The specialized workflow runs Ubuntu/Windows × Python 3.11/3.12 on GitHub-hosted
runners, checks exact PR head checkout, compares collected and actually executed
node IDs and JUnit identities, rejects skips/xfail/errors/failures, then exports
SHA256 receipts. Working-tree LF/CRLF equivalence is checked against exact Git
blobs; receipts retain both Git-blob and actual working-byte hashes explicitly.
These hashes are software test evidence, not host attestation.

AST/import tests restrict the validator to pure JSON/hash/lexical-path operations;
source tests freeze inherited LSA and physical harness bytes. This structural
guard is not a sandbox against malicious repository code or a compromised runner.
Only the specialized pure workflow is permitted for this new branch; inherited
infrastructure jobs explicitly exclude it before any service provisioning. Five
older workflow tests recognize the additional branch-scoped pure workflow while
retaining their no-services/no-infrastructure assertions. No native compilation,
PowerShell collector, installer or physical harness is executed by this workflow.

## Audit findings and readiness

| Priority | Finding / disposition |
|---|---|
| P0 | No concrete new P0 identified within this offline implementation; no claim of a full platform audit |
| P2 — fixed | AI review reproduced false model PASS when a toolchain file equalled TEMP/evidence or was a required ancestor. Equality and both containment directions are now rejected. Three failing reproducers became green; five regression positions cover roots and ancestor-file collisions. Host flags remained blocked before and after the fix |
| P1 | Supplied LS5 Source/shared TEMP observations remain unsafe for elevated compilation. This work does not inspect or fix them. Physical/host GO is blocked |
| P1 | Input authenticity, actual token/effective group access, protected custody and TOCTOU resistance are unproven. A synthetic PASS cannot close these blockers |
| P2 | ACL/path/volume model is conservative and incomplete for real Windows descriptors and dependency resolution. Schema success is not semantic success or host proof |
| P2 | Replay, trusted time, durable evidence authenticity and privileged attacker resistance are not implemented here; offline input digests do not provide them |

Offline model GO is conditional on exact-head green specialized CI and independent
review of this limited contract. **Host staging, L1/L2, Execute and physical tests:
NO-GO.** Human preparation still requires approved topology and trusted identities,
independent host observation/authorization procedures, fully pinned source/toolchain
inventory, verified ancestor ownership/access, fresh private TEMP/evidence, and
separate STOP/recovery/cleanup approval. No automatic transition is provided.

Development rollback is reverting this PR's commits. No directories, ACLs,
accounts, services, policies, PostgreSQL data or installed releases were changed;
there is no host cleanup or provisioning recipe to execute.
