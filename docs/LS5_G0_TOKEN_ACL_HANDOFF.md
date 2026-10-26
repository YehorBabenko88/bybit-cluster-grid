# GPT-1 independent G0 token/ACL/handle acceptance — Codex handoff

Baseline source: PR239 independent branch; PR244 exact HEAD `1d06bf8104c25642133ae76de9996eb098514e59`. This is a **design and synthetic model**, not physical attestation.

## Minimal native evidence requirements

1. On each LS5/PC4 host, under separately approved read-only G0 scope, acquire **one stable process/token handle identity** with process creation time, image file identity and verified parent/Job ancestry. PID alone cannot prove ownership. Unknown, reused PID, impersonation or unavailable handle => BLOCKED.
2. Bind TokenUser, TokenGroups (enabled/deny-only/restricted attributes), TokenIntegrityLevel, TokenElevation, token type, impersonation level, token privileges and account enabled state to the same token. PC4 Collector/Storage `Enabled=true` is an observation only; confirm least-privilege intent and all effective deny groups. Filtered-admin and impersonation must fail closed.
3. Read owner/DACL, inherited ACE and parent DELETE_CHILD, WRITE_DAC/WRITE_OWNER, reparse/hardlinks and all ancestor descriptors using stable file handles. Perform native **effective AccessCheck** with the correct token and desired masks, not string-based ACE matching. SACL/mandatory label read failure => UNKNOWN, not absence.
4. Verify Grid source and Python loader closure: launcher, interpreter, pyvenv.cfg, sitecustomize, .pth, site-packages, native extension DLLs, PowerShell modules, manifest, configuration, PATH/PYTHONPATH, cwd, TEMP/TMP and any inherited writable roots. A digest from the same compromised source is not independent provenance.
5. Never use existing LS5 ProgramData paths, installed tasks, 8765 listener, existing PGDATA or shared secrets as disposable G1 inputs. G0 does not mutate ACLs, services, tasks or processes.

## Offline contract and reproducible tests

`installer/ls5_token_acl_claims.py` and `tests/test_ls5_token_acl_claims.py` check untrusted observation shape, strict booleans, canonical bounded SID, filtered-admin, impersonation, incomplete token groups, missing effective access, parent DELETE_CHILD, WRITE_DAC/WRITE_OWNER, reparse, PID identity, parent/tree and loader closure. Run:

```powershell
py -3.11 -m pytest -q -ra tests/test_ls5_token_acl_claims.py tests/test_ls5_coexistence_safety.py
```

A model-pass still reports `host_verified=false`, `effective_access_verified=false`, `execute_authorized=false`, `cleanup_authorized=false` and `bootstrap_physical_readiness=NO-GO`. It is not a Windows AccessCheck implementation.

## Minimum independent Codex integration patch

Do **not** import these synthetic booleans as physical evidence. Native G0 must emit a versioned, signed or independently authenticated, nonce/run-bound receipt including token/file handle identity and AccessCheck outcome; a separate verifier checks source/manifest/handle binding, negative conditions and evidence provenance. Missing native AccessCheck or inability to prove same token and file identity means BLOCKED. Physical G1 must remain separately authorized after G0 and native observer review.

**P0:** LS5 inherited Users rights/effective AccessCheck and source custody, PC4 account/token evidence, native process-handle proof. **P1:** Windows Job containment and real Python loader closure. **P2:** durable signed receipt/anti-replay and exact-head cross-PR schema agreement.

`BOOTSTRAP_PHYSICAL_READINESS=BLOCKED`. G0 read-only review only; G1 Execute/Cleanup NOT_AUTHORIZED; physical 0/10 NOT_RUN; deployment NO-GO.
