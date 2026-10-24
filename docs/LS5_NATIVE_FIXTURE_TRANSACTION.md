# Native transaction fixture: executable prototype, never production authority

Physical PC4 **0/10 NOT_RUN**. Execute/Cleanup **NOT_AUTHORIZED**. Deployment **NO-GO**.

## Boundary

`installer/native-acl-transaction-fixture` is a separate test executable. The observer has no mutator and the production PowerShell Apply refusal is unchanged. The test accepts only `--hosted-fixture-tests` or pure `--model-tests`, never a target path, original journal, replacement ACL or approval file. Environment restrictions prevent accidental execution; environment strings are forgeable and are not attestation or an adversarial sandbox. Do not copy/run this prototype on LS5/PC4.

Only GitHub-hosted GUID fixtures are permitted. The executable opens the local physical-volume root and every RUNNER_TEMP ancestor by retained no-delete handles, rejects reparses/non-NTFS/identity uncertainty, and creates a new GUID directory using native FILE_CREATE with a protected DACL in the creation descriptor. A collision is an error; no existing object is adopted or overwritten. It creates an empty target and journal, both no-sharing, under that original directory handle. No credentials, accounts, tasks, service, policies, PostgreSQL or existing Grid resources are touched. Fixtures are retained, not recursively cleaned.

All ACL mutation is DACL-only, by handle, on that newly created empty leaf. There is no directory ACL propagation, ownership takeover, privilege enable, task activation or production rollback. Original and intended descriptors both grant access only to SYSTEM and the ephemeral fixture custodian. This is not evidence for a non-admin user: the hosted runner token may be elevated.

## Journal implementation and explicit limits

PREPARED → INTENT → APPLIED → VERIFIED → COMMITTED are ordered. A complete canonical record is written and FlushFileBuffers is checked before advancing; INTENT is flushed before SetSecurityInfo. Identity, descriptors, root/ancestor/journal custody and readback are checked on retained handles. Original/New owner/group/DACL bytes, target/root IDs, run UUID, exact HEAD, Actions run/attempt, sequence and prior digest are bound. Duplicate keys, unknown fields, noncanonical records, missing/truncated/torn tails, reordering, altered payload, bad digest and stale prefix against the expected external anchor are rejected.

The journal DACL is protected at creation. A hash chain detects corruption **but is not authentication**; the expected anchor in these tests is harness memory, not a durable independent witness. Same-user/privileged writer threats, hostile administrator, storage snapshot rollback, enrollment and signed approval remain unproven. File flush success is not a power-loss experiment, nor proof that ACL metadata, directory creation/publication or physical storage are durable.

Simulated recovery releases/reopens child handles while the harness retains root/ancestor custody. It is **not** a process-kill, OS-crash or power-loss test. On recovery the journal/target identities, descriptor and anchored chain must match. Original ACL after APPLIED/VERIFIED/COMMITTED without RESTORE_INTENT is an unexplained rollback and blocks. Only a hard-coded fixture approval can write/flush RESTORE_INTENT, restore this known safe fixture original, read it back and append/flush RESTORED. A truncated or divergent journal never authorizes repair. Real Apply/Rollback remains unimplemented and unauthorized.

The artifact includes seven native journal-byte/readback snapshots (commit and six simulated barriers). A separate Python reader recomputes raw record digests, checks identities and terminal phase against the scenario. These are only self-consistency checks of disposable CI observations.

## Tests and receipts

- 31 observer assertions, including parent descriptor drift, a surviving pre-existing data writer that **does not** acquire custody PASS, and a real DELETE-access handle producing STATUS_SHARING_VIOLATION.
- 42 pure observer policy cases, without native APIs.
- 20 native transaction fixture cases: protected native creation, collision, metadata/data-read/data-write exclusion, concurrent moves, durable record/readback, six simulated restart barriers, descriptor drift, labelled injected flush refusal and an actually truncated fixture journal.
- 30 pure journal-model cases, including replay/head/attempt/ABA, truncation, transitions, stale anchor and unexplained old state after commit.
- Frozen Python receipt/negative tests in `native_observer_inventory.json`; no skips/xfail accepted.

The workflow compiles both binaries, runs PowerShell 5.1 and 7 × Python 3.11/3.12, freezes inventories and hashes complete source/binary/artifact closures. All JUnit suites bind head/run/attempt; JSONL does too. `native_observer_artifacts.py` reads a downloaded ZIP in memory (no extraction/execution), independently compares the externally supplied GitHub API digest, source Git blobs, artifact/binary hashes, JUnit and raw JSON/JSONL. API metadata supplied as a local file is not authenticated by this offline reader. A second reviewer must obtain it independently.

Example **offline inspection only**, after actual CI success and artifact download:

```powershell
python -m installer.native_observer_artifacts --zip <download.zip> --metadata <github-api-run-and-artifact.json> --head <exact-head> --run <run-id> --attempt <attempt> --name <exact-artifact-name>
```

The metadata JSON has `run` (GitHub run API response) and `artifact` (separate artifact API response). Missing/mismatched ZIP digest, non-success run or absent artifacts blocks. Do not manufacture these inputs to satisfy acceptance.

## Contract reconciliation snapshots

PR #239 observed `bc56108c33acd79af0dfb07fb03fdf299f6ba92c` proposes `grid-ls5-source-handoff-1`. The current observer does **not** consume an authenticated manifest/nonce or attest executable/import/DLL closure, SACL/MIC, old writers or task quiescence. Its receipt explicitly says `bootstrap_handoff=BLOCKED_NOT_CONSUMED`. These P0 prerequisites cannot be filled with self-reported booleans or an adapter that silently invents measurements. G1/G2 remain BLOCKED.

PR #242 observed `265b72bb7039d5672c8fc5171556cbb33b2b674b` has generic `results.xml/events.jsonl` and head/run/attempt/ZIP chain contracts. Raw native records have a different explicit schema and must not be passed off as the generic metadata. Map the exact raw JUnit suite attributes and receipt context into its evidence-chain review; bind artifact ID and independent ZIP digest from the API. The generic acceptance return is always BLOCKED and cannot approve native custody. Any future projection needs a reviewed versioned adapter and negative tests; no silent physical-PASS projection is implemented here. The pure GitHub source snapshots have disjoint ownership; combined runtime behavior has not been tested or merged.

## Remaining blockers

Actual exact-head hosted artifacts are required before native CI acceptance. Production remains blocked by independent trusted rebuild/provenance, all relevant principals/MIC/restricted tokens/privileges, prior writable/mapped handles and task/process quiescence, complete six-release/import/config/DLL scope, authenticated durable journal/approval, independent epoch witness and actual controlled crash/storage-failure testing. Human authorization and review remain separate. Neither a fixture test nor AI review grants physical permissions.

Native API references: [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo), [NtCreateFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntcreatefile), [FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers).
