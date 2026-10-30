# S0 bootstrap closure implementation plan

> **For agentic workers:** Use test-driven, isolated component work; root integrates and verifies exact-head CI. No physical mutation is authorized.

**Goal:** Close the source bootstrap/token/checklist tooling gaps for a future separately authorized LS5/PC4 S0.

**Architecture:** Authenticity starts with an externally reviewed ZIP SHA256, captured through a read-only/no-delete handle. Trusted stock Windows PowerShell loads the native assembly bytes directly from that authenticated ZIP; no unverified extracted Python, local compiler, ScriptBlock/iex or policy bypass. Native code validates the complete archive before writes, pins the actual LocalAppData ancestor chain, creates only fresh protected objects, and atomically publishes without replacing anything. Failed transactions remain private/incomplete and are never auto-deleted or adopted.

**Tech stack:** C#5/.NET Framework4.8-compatible APIs also loadable from PowerShell7; Win32 handles/security APIs; existing Python S0 code; offline tests and disposable GitHub-hosted Windows fixtures.

**Spec:** user task and PR244 coordinator comment6478072416; baseline5b8da4f1ca8000f7fd20dc146f0a1172c217803d.

## Constraints / decisions

- Work only PR244 branch; no main/other agent branches/merge/deployment.
- No physical stage/start/stop/cleanup, account/ACL/service/task/network/PostgreSQL changes.
- Use existing current primary token; Medium, non-elevated, Admin not enabled, only approved enabled privileges. Unknown API/layout/identity is BLOCKED. Raw host SID/token evidence stays protected/private.
- Public package: full manifest, source.zip closure, all hashes/sizes, unique safe names, bounded extraction and exact HEAD. Fresh per-user GridS0Package UUID targets only; fail if existing or unsafe parent.
- Source ZIP may be in an untrusted download directory only because immutable captured bytes are authenticated before any assembly load. Target ancestry must be protected and pinned before creation.
- Initial input plan and PC4 role input use separate fresh GridS0Input UUID roots. PairRoot and RoleRoot have distinct command-manifest fields and are never inferred by nesting guesses.
- Private SSH transfer uses pinned existing host key, no password/credential command arguments, no remote shell policy changes, no scp into shared paths. Source/destination content is run/head/hash-bound and writes only to a fresh pre-created protected slot. SSH admin transport is never evidence of a standard execution token.
- Default PlanOnly; each physical mutation group needs separate explicit owner authorization. All20G1 phases remain BLOCKED/null argv.

## Implementation tasks

- [ ] Native read-only TokenObserver DTO/decoder/RequireStandard; actual primary SID, all groups+attributes, IL/elevation, privilege names+flags; bounded fault tests.
- [ ] Native Bootstrap: strict JSON/archive validation, owner/DACL/reparse/file identity/ancestor custody, atomic fresh publication, protected private evidence, no overwrite or automatic cleanup; NTFS disposable fixtures/faults.
- [ ] Authenticated bootstrap PowerShell entry and clipboard-safe inline loader; no execution from unverified extracted source. Include all native sources in one hosted-built pinned library.
- [ ] Opaque protected receive-slot and private six-file PC4 role export/import; SSH transport command validation and exact host fingerprint; independent mutation gates.
- [ ] Offline command manifest with PackageRoot/InputRoot/PairRoot/RoleRoot explicit, read-only/approval/effects/STOP fields; requested phase order.
- [ ] Independent reproducible acceptance checklist and offline artifact checker that never grants authorization, including stale/fake PASS negative tests.
- [ ] Focused offline/PS checks, new hosted native cases and exact-head packaging gate; no redundant manual reruns of unchanged market tests.
- [ ] Publish exact SHA/artifact digests/commands/remaining physical gates. No physical PASS claims.

## Review focus

- The very first loaded executable must already be authenticated; post-import verification is too late.
- Windows JSON implementations must reject duplicate/unknown fields and numeric/boolean coercion.
- Rename must be no-replace and handle-bound, with stable parent custody and no open-child rename ambiguity.
- Elevated SSH file delivery must not turn into runtime token approval or leak private key bytes through inherited default ACLs.
- Partial writes/retries/concurrency must preserve existing objects and never manufacture a completed receipt.
