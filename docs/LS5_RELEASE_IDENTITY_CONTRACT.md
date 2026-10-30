# Release identity contract for PR239 ↔ PR244

Reviewed: PR239 source HEAD prior to this contract `1796402dc92b9507aa3e863f73d3b5fb8df99cfe`; PR244 `79049906cb004e324bec5ef4cc53b85381cab83a`.

## Decision

**Do not hardcode a historical active release ID in the generic offline validator.** An immutable, independently authenticated policy for a *specific run* must pin the exact 40-hex release SHA. Observation must match it. Manifest inventory must include the executable at `releases/<active_release>/grid/coordinator.py` with expected SHA256 and a closed runtime dependency inventory. The source HEAD and release SHA are different identities and must be separately bound by trusted provenance; matching self-reported JSON is not authentication.

PR244's `VERSION = 9ab1f5...` check blocks all future approved releases. PR239's dynamic policy pin is the correct **model-level** compatibility rule, but is not sufficient for a real GO without external policy signature/source acquisition/nonce and native file-handle custody.

## Minimal Codex patch in PR244 (do not cherry-pick blindly)

Replace:
```python
if p["active_release"] != VERSION or o["active_release"] != VERSION:
    raise ValueError("ACTIVE_RELEASE")
```
with:
```python
release = p["active_release"]
if type(release) is not str or not COMMIT.fullmatch(release) or o["active_release"] != release:
    raise ValueError("ACTIVE_RELEASE")
```
Ensure mandatory coordinator executable inventory uses `release` rather than `VERSION`. Do not relax SHA256, file set equality, ancestry, owner, DLL/Python closure or host authorization guards. Add tests for stale manifest, wrong observation release, missing release-specific executable, source HEAD mismatch and interrupted rollback.

## Future authenticated envelope

The *trusted-source provider*, not the validator's caller, must authenticate a canonical policy containing: exact candidate source HEAD, release SHA, release tree SHA256, manifest SHA256, full executable closure, signature verification key identity, nonce/run ID, expected task/launcher roles and verified root identity. Native observer must independently bind the same nonce, file IDs, owner/DACL/SACL and manifest digest. Unknown, stale, mismatched or replayed receipt => BLOCKED.

## Status

This is an offline contract and a minimal cross-PR patch proposal. It does not authorize Windows execution, release switching, cleanup, service or Scheduled Task modification. `BOOTSTRAP_PHYSICAL_READINESS=BLOCKED`; `G1=NOT_AUTHORIZED`; physical PC4 `0/10 NOT_RUN`; deployment `NO-GO`.
