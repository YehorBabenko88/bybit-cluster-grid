# Native ACL transaction executor — separate design, no implementation authority

**DESIGN_ONLY. Apply/Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO. Physical PC4 0/10 NOT_RUN.** The observer does not implement this design. Production refusals remain unconditional; no migration, task activation, secret rotation, deployment, deletion or restoration is implicit.

A separate [native GUID fixture prototype](LS5_NATIVE_FIXTURE_TRANSACTION.md) now implements limited create/DACL/journal/readback and simulated recovery code for hosted CI only. It does not satisfy the production trust, authentication, quiescence or crash-durability prerequisites of this design. No production transaction hook is enabled.

## Trust and prerequisites

The executor must be a separately reviewed signed native component from independently protected source/toolchain, outside the writable Grid tree. A matching old launcher hash or observer exit0 is insufficient. Its protected approval manifest must bind source HEAD, binary closure, explicit installation scope, volume/file identities, service/custodian SIDs, expected descriptors, independent observer identity, operator authority and expiration/epoch policy.

Before the first mutation, independently prove all relevant token/group/privilege/MIC rights, ancestor deletion/replacement exclusions, no unknown reparse/link/aliases, and a complete code/config/import/DLL/data scope. Identify all six releases and previous/staging/fallback paths. Independently establish writer/process/task/handle quiescence. Never infer that an account/task/directory belongs exclusively to Grid. Unknown state blocks the transaction.

Acquire the existing release mutex and keep it through recovery/commit. Reuse Runtime Guard immediately before first write, but do not equate that scan to writer exclusion. Hold stable handles from verified volume roots through the entire approved scope. A native mutator must operate on those handles with minimum rights, not use path-based descriptor setters or reopen a path as proof. Granting data writers access to executable/deserialization inputs requires a separate contract.

No process termination, privilege enabling, ownership takeover or policy change is automatic. A hostile administrator/kernel can defeat a same-host software policy; the project must either exclude that adversary under documented human controls or move the experiment to independently controlled disposable isolation. No false guarantee is acceptable.

## Durable journal contract

Storage is outside the mutable code/data tree with independently verified custody and no reparse/alias reachability. The journal is append-only for the executor identity and read-only for independent observers. Atomic publication, append durability and storage failure semantics require actual Windows crash tests; in-memory model success cannot approve them.

Each canonical, bounded, versioned record binds transaction/run UUID, monotonic sequence, previous authenticated record digest, independently approved epoch, source/binary hashes, approval-manifest digest, operation index, volume/128-bit file identity, exact original/current/intended owner/group/DACL, any separately authorized audit descriptor, data hash when required, observer receipt and constant error/state. Do not include `.env` values, passwords, tokens or command-line credentials. Protect opaque descriptor backups as privileged evidence.

Use an established authenticated-envelope implementation/library and protected signing identity; do not invent cryptography. Key enrollment/revocation and independent witness verification are explicit inputs. A hash chain alone is not authentication; an authenticated same-disk journal alone is not anti-rollback. An independent durable epoch/receipt witness is required to detect restoring an older valid journal and data snapshot. Until trusted time/epoch/key custody/witness availability are proven, durable anti-rollback remains BLOCKED. No automatic network/witness calls are part of this stage.

## State machine and write barriers

| State / transition | Durable action before next step | Required invariant |
|---|---|---|
| BLOCKED -> PREPARED | Publish authenticated manifest + complete originals and observer receipt; flush data and publication metadata with a proven Windows protocol | No descriptor mutation yet; all proof gates satisfied |
| PREPARED -> INTENT(i) | Append/flush authenticated per-object original/current/intended descriptor and stable identity | Original handle and exact pre-state still match; runtime/writer exclusion held |
| INTENT(i) -> APPLIED(i) | Set approved descriptor by original handle; read back by same handle and independent observer; append/flush post-state receipt | Only allowlisted object changed; token/service rights preserved |
| APPLIED(i) -> VERIFIED(i) | Flush verified receipt and witness epoch acknowledgement under approved availability policy | No claim of durability without both local storage and required witness barrier |
| VERIFIED(last) -> COMMITTED | Revalidate full scope and unrelated-resource invariants; append/flush commit and independent receipt | All operations verified, no activation authority |
| any uncertain/error state -> STOPPED | Preserve durable diagnostics without continuing operations | Handles/mutex released only after a reviewed safe stop; tasks remain disabled |

`COMMITTED` means only the approved descriptor transaction reached its verified barrier. It does not approve poisoned code, revoke pre-existing handles, rotate exposed credentials, authorize real collection/trading or enable any task. Trusted rebuild and separately approved secret response are independent gates.

## Recovery decisions

Recovery starts read-only with independently trusted verifier/executable. Verify full journal authentication, chain, strict sequence, schema, run/epoch, source/binary/approval digests, witness position, storage identity and scope before acquiring write-capable handles. Truncation, duplicate/conflicting sequence, stale valid prefix, unknown records, missing witness, bad signature or substituted store means BLOCKED/manual recovery.

Reacquire the exact approved object identity through verified parents; compare current descriptor with the authenticated original and intended post-state. Never restore to a pathname replacement or accept file-ID equality as proof of trustworthy acquisition. A same-host privileged adversary or storage rollback needs external evidence; do not silently downgrade to a checksum-only decision.

| Crash point | Safe recovery classification |
|---|---|
| Before durable PREPARED | No authorized mutation; retain evidence, reject abandoned/untrusted material |
| PREPARED, no durable INTENT | Verify no mutation; remain stopped pending independent review |
| INTENT durable, mutation not observed | Current original may mean not applied; it is not permission to apply automatically |
| Mutation performed, APPLIED not durable | Current intended descriptor may indicate completion; classify UNCERTAIN until independent receipt and exact identity are established |
| APPLIED durable, independent/witness receipt absent | Local post-state insufficient; remain BLOCKED |
| VERIFIED prefix with later interruption | Verify every prefix object and remaining originals; no inferred suffix completion |
| COMMITTED durable but stale/missing witness epoch | Potential rollback/replay; BLOCKED |
| Restoration interrupted or current state diverges | STOP; preserve evidence; no recursive repair/retry loop |

Rollback requires a new explicit per-object approval and native identity/custody proof. An original Users-write/readable-secret descriptor is unsafe: it must never become an automatically accepted ready state. Prefer containment and independently trusted reconstruction. Do not delete releases/WAL, reset system-root ACLs, disable unknown accounts, alter unrelated services or start anything as a recovery side effect.

## Future independent acceptance, all currently BLOCKED

Require controlled Windows crash/fault tests at every durable barrier and mutation boundary; disk-full/I/O denial/torn/truncated/reordered/duplicated records; forged and old valid signatures/epochs; key substitution; concurrent executors and abandoned mutex; namespace/ancestor/hardlink/descriptor races; stale handle reuse; readback/observer disagreement; independent store/witness loss; original insecure descriptors; unsupported Windows/API/filesystem behavior; preserved data and unrelated resources. Use disposable owned fixtures and established keys only; physical experimentation requires separate authorization.

The current read-only observer's22 native-layout cases plus six labelled injected refusals,40 pure managed cases and32 Python tests establish neither durability nor mutator safety. No Apply implementation or enable flag is added by this design.
