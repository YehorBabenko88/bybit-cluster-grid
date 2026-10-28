# S0 independent acceptance — offline evidence is never permission

Status: physical **0/10 NOT_RUN**; all **20 G1 gates BLOCKED**; Execute and Cleanup **NOT_AUTHORIZED**; deployment **NO-GO**. GPT-4 availability is irrelevant: a named independent human reviewer must record identity, exact source/artifact pins, findings and explicit owner approvals in a protected review record outside this checker. A model or green checker cannot provide that permission.

Use PASS / FAIL / BLOCKED for every row below. PASS means the specified evidence was reviewed; any missing, ambiguous, stale or inaccessible fact is BLOCKED. Contradiction/tampering is FAIL. Neither permits physical work. Record reviewer identity, date, source of each independent pin and evidence location privately. Keep raw machine SIDs, token dumps, private keys and transfer records protected; never upload them to chat, Git or public artifacts.

| Review | PASS criterion | FAIL / BLOCKED trigger |
|---|---|---|
| Source identity | Independently inspect exact 40-hex HEAD and tree and review changed code; source bytes are exact Git object bytes, including LF bytes | Branch name only, checkout CRLF hashes, a model assertion or unreviewed source |
| Authentic hosted artifact | Independently obtain GitHub API artifact SHA256, repository, workflow/job `s0-windows`, exact head, successful run ID and attempt; keep original downloaded ZIP bytes | A digest copied only from inside the same ZIP, expired/missing API digest, mismatched run/attempt/head |
| Package closure | Original outer ZIP digest, inner receipt size/hash/context, original package ZIP, every manifest member size/hash, exact complete closure and independently reviewed source pins agree | Extra/missing/duplicate/case-colliding/unsafe members, changed payload, rebound manifest or authority other than literal false |
| Hosted tests | Both shell artifacts and four offline OS/Python artifacts match reviewed inventory; no failure/error/skip, exact test cases, explicit subtest counts and exact source/run/attempt context | Stale JUnit, omitted case/subtest, a summary PASS without original receipts |
| Native hosted facts | Fourteen token probes plus three observations show standard medium, unelevated, Admin disabled, same observed SID, distinct PID/creation pairs, actual Job membership flags 8200 and active limit 1; normal/descendant exit zero; deadline `timed_out=true` | Missing/unknown/coerced facts, reused identity, bad Job flags; deadline exit zero is legitimate when timed_out=true |
| Scope | Hosted fixture and public observations are labeled hosted, partial component pairs agree in run/head/tree/counters/heartbeats | Any hosted fixture claimed as physical PASS; these observations provide no privileged-admin isolation proof |
| Physical identity (private) | Independently map logical LS5/PC4 to exact observed NetBIOS names, literal addresses, full distinct operator SIDs, approved port/routes | LS5/PC5 narrative substitution, aliases normalized, guessed host or identity |
| Physical token (read only) | Approved reviewer checks actual primary token SID, elevation, integrity, every group attribute and privilege; Medium/unelevated/Admin not enabled and only ordinary standard privilege names present (ChangeNotify, Shutdown, IncreaseWorkingSet, TimeZone, Undock); only SeChangeNotifyPrivilege may be enabled | SSH Administrators membership treated as standard execution evidence, unknown native API/layout, missing privilege/group attributes |
| Bootstrap custody | Review authentic-first assembly loading, captured immutable original bytes, bounded complete archive validation before writes, actual LocalAppData ancestry and owner/DACL/reparse/file identities | Loading extracted/unverified Python/DLL first, inferred custody from ZIP hash alone, repairs to existing ACLs |
| Atomic staging | Fresh protected UUID target; pinned parent handle and stable ancestry; no-replace atomic publication; complete receipts and original source.zip closure | Existing/adopted target, partial publication, replacing a prior target, auto-cleanup/retry/adoption |
| Input/roots | Explicit PackageRoot/InputRoot/PairRoot/RoleRoot; pair GridS0 UUID and role child are distinct; initial private plan and received PC4 six-file input separately validated | Guessing role root by nesting, copied prepared marker, missing fresh local PC4 Prepare |
| Transfer | Separate approval for pinned existing full SSH host-key fingerprint and authenticated encrypted channel; only reviewed PC4 six files into fresh protected receiving slot | Password/key in argv, shared target, unpinned host key, LS5 key/prepared marker transferred |
| Mutation authorization | Separate explicit owner authorization for each preparation, transfer, execution, stop or cleanup group after independent review and complete G0 | Treating checklist PASS, PlanOnly or hosted results as approval |
| Execution scope | Exact 300-second standalone public BTCUSDT S0; fixed public Bybit topics; foreground owned process, no DB/Grid/service/task/ACL/account changes | Extending budgets, private endpoints, production entrypoints or weakening checks |
| STOP | Uncertainty, incomplete window, operator stop or partial output is STOP/PARTIAL; preserve private partial evidence | Promoting partial to PASS, killing unrelated PID, automatic cleanup |

The public raw sample is a hash-only integrity observation when raw bytes are not supplied: it cannot independently establish message contents, subscription ordering, a physical collection window, or replayed market counters. Review the original restricted raw evidence in its authorized location if needed. Hashes attest byte consistency only after authentic provenance has been established.

## Reproducible offline checker

`tools/s0_independent_acceptance.py` is a separately implemented standard-library checker. It imports no producer verifier, performs no network/native/host queries, starts no process and extracts or executes no ZIP member. It reads one original hosted artifact ZIP and inner receipt/package ZIP in memory. Limits: 512 MiB outer/archive aggregate, 64 MiB per member, 20,000 members; encrypted, symlink, unsafe, duplicate and case-colliding members fail. Requirements version 4 requires the implemented TokenObserver, Bootstrap,
Inputs, bootstrap loader and command/checklist sources, plus closed original
bootstrap/token receipts with raw-byte hashes and exact context/source bindings.
Older packages without these records are unsupported and BLOCKED.
Source presence alone establishes no working bootstrap path or physical readiness. It defines mandatory source files rather than freezing current payload/source counts; additional reviewed source pins are verified through the same independent byte provider.

Use a separate reviewed exact Git object byte export directory, whose contents and HEAD/tree association were independently established. Do not execute a bundled interpreter or scripts from the candidate package. Run a trusted existing Python:

```text
python -m tools.s0_independent_acceptance --head <reviewed40hex> --tree <reviewed40hex> --run-id <GitHubRun> --attempt <GitHubAttempt> --outer-sha256 <independentlyObtainedGitHubApiArtifactDigest> --artifact <originalArtifactZip> --source-bytes <reviewedExactGitObjectByteDirectory>
```

The CLI takes all context explicitly; environment variables cannot spoof it. A callable `check(..., provider)` accepts a reviewer-supplied pure source-byte provider; it never runs Git. The checker verifies hosted package closure, external source bytes, hosted inventory/JUnit, native facts and paired component summaries. It also checks public probe context, closed classification and sample hash/size/topic counts, without claiming raw-content replay. Review the four offline receipts and public probe/raw limitations manually using the rows above; this single-hosted-artifact checker is deliberately not a complete review of all CI artifacts or physical evidence.

Only successful status: `OFFLINE_EVIDENCE_CHECK_PASS_NOT_APPROVAL`, always `approval=BLOCKED`. A failure produces a closed BLOCKED result without printing private input values. The checker does not record human approval or allow an approval flag. Independently validate both PowerShell artifacts and record all manual rows, then keep the actual human authorization in the protected external record. Physical readiness remains 0/10 NOT_RUN until a separately authorized physical review supplies it.


## Existing command sequence and remaining integration gaps

The existing package sequence is the manual sequence in [PHYSICAL_SMOKE_S0.md](PHYSICAL_SMOKE_S0.md): establish complete private G0 and independent review; authenticate the original hosted package; obtain separate preparation/staging authorization; use a separately reviewed protected staging procedure; then the wrapper supports Plan, local Prepare, prepared-role Preflight and separately approved Execute. PairRoot is the new GridS0 UUID root passed for Prepare; RoleRoot is its local LS5 or PC4 child passed for Preflight/Execute. Plan cannot bootstrap an absent root or grant authority.

This integration supplies an authentic-first literal PowerShell loader and
`physical-smoke-s0-bootstrap.ps1` convenience entry for a protected checkout,
plus native atomic package/plan-input staging and six-file archive import.
Their availability is not a Windows test result or owner authorization.
There is no protected `physical-smoke-s0-transfer.ps1` sender/receiver.
The private six-file transfer remains BLOCKED pending implementation, exact-head
integration evidence, independent review and separate owner approval. No plain
scp, shared input or inherited-ACL extraction fallback is authorized.

The checker tests are listed explicitly in `integration/s0_inventory.json`; the existing `s0-offline` four-job matrix executes them and checks exact node/JUnit/subtest inventory. This is an offline evidence gate only. It does not run the independent artifact CLI against a genuinely authenticated downloaded outer artifact automatically, and does not replace an external human obtaining the GitHub API digest.


The reviewed literal initial ZIP loader is in
`PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md`; its source body is checked against
`installer/physical-smoke-s0-bootstrap.ps1`. Native input staging/import are not
a protected SSH receiver. Keep transfer BLOCKED until its concrete implementation
and independent tests exist. Never infer owner authorization from these tools.

The token presence policy rejects elevated or unknown privilege names even when
disabled: assigned disabled privileges can be re-enabled by the token holder.
Only ChangeNotify, Shutdown, IncreaseWorkingSet, TimeZone and Undock may be
present, and only ChangeNotify may be enabled. Unknown membership/effective ACL
rights remain a separate private G0 review; this predicate is not a sandbox.

Version 4 additionally requires actual PlanOnly invocation of the authentic-first
bootstrap loader inside the hosted Medium shell, with PowerShell 5 and 7 matrix
cells. Parsing script syntax or executing a C# helper under a shell is not this
observation. The new boolean must be literal true, with the loader test source
independently pinned; older v3 artifacts do not satisfy this new requirement.
