# LS5 Trusted Bootstrap — independent offline trust boundary

Base PR #237 exact HEAD `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`.
This branch does not modify native ACL observer/executor (#238), tasks, Windows ACLs, release switching, recovery or any physical system.

## Findings and boundaries

**P0: supplied LS5 Grid ProgramData, installer, Python runtime, six release directories and ancestor paths were writable by untrusted principals.** A SYSTEM Scheduled Task can execute injected launcher/Python/DLL content. Previously stored SHA or release manifest is not a publisher signature. Active release `9ab1f5b85ec471ea21ec89f1b76740c0b01537b6` and six-release inventory are owner-reported, not independently authenticated host facts. The tasks `PowerGridForecastTask` and `grid_pg_test` are unclassified; no ownership, disable or cleanup authority is inferred.

The existing bootstrap and install scripts on #237 start in PlanOnly and explicitly throw on Apply. Their unreachable legacy bodies nevertheless demonstrate the prior risk: bootstrap creates inheriting ProgramData/ProgramFiles directories, extracts archives and copies Python, runs a preexisting interpreter, creates venv and installs pip requirements; install copies launchers and would register SYSTEM/Highest scheduled tasks. Existing release mutex, runtime guard, manifest checks, atomic pointer and prepared/committed recovery protect transaction sequencing but **do not authenticate code or guarantee ACL custody**. Never activate these paths on LS5 before independent trust proof.

## Offline model

`installer.trusted_bootstrap.assess(policy_raw, observation_raw)` checks strict synthetic JSON:
- Exact pinned commit and active release, closed schema and complete *declared* executable inventory; SHA256 equality, no duplicate/aliased paths, no hardlinks/reparse, asserted protected owners/ACL/ancestors.
- Explicit interpreter, `pyvenv.cfg`, site-packages input, DLL search roots and import closure; reject PYTHONPATH/PYTHONHOME and other Python environment injection, untrusted PATH and current directory, user site and non-isolated interpreter.
- Asserted fresh trusted rebuild, no pre-existing writers, stable handles, independently authenticated provenance, disabled Grid tasks, classified unrelated tasks and recovery disabled.
- Always `status=BLOCKED`, `host_verified=false`, `execute_authorized=false`, `cleanup_authorized=false`, `deployment_authorized=false`, `physical_tests=0/10 NOT_RUN`, even when `model_status=OFFLINE_MODEL_PASS`.

**The model cannot prove inventory completeness, signatures, ACLs, code provenance, token groups, loader search order, native handles or physical facts.** Consistent forged JSON can model-pass. Neither this model nor GitHub-hosted CI is a bootstrap authority. This is deliberately a separate module, not imported into the existing launchers or native ACL executor.

## Future physical restoration — NOT AUTHORIZED

R0: independent written owner authorization, identify all tasks including PowerGridForecastTask/grid_pg_test, disable/contain execution by separately authorized procedure, classify external owners and establish STOP authority.

R1: acquire an independently trusted, immutable bootstrap executable and full pinned source provenance from outside writable Grid roots. Verify publisher signatures and independent release manifest/tree digests, trusted root keys, complete transitive Python/native DLL/import closure and authentic build receipts. A SHA read from the same compromised directory is not a trust anchor.

R2: after separately approved native ACL repair, use a new protected, independently owned staging root. Independently inspect volume/file IDs, parent DELETE_CHILD, owner/DACL/SACL, inherited ACE, WRITE_DAC/WRITE_OWNER, hardlinks/reparse, existing write handles, service tokens and effective rights. No path-only TOCTOU assumption.

R3: quarantine suspect release/runtime inputs as evidence under separate authority, do not delete or overwrite them. Rebuild all executable inputs from trusted signed artifacts in the protected root; include Python interpreter, pyvenv.cfg, .pth, sitecustomize, site-packages, native extension modules, DLLs, launcher scripts and manifests. Do not reuse old venv or pip-installed dependencies based on requirements hash alone.

R4: verify release switch and recovery paths before any activation: trusted current.version, pinned six releases, no rollback to poisoned previous/fallback, trusted journal and mutex custody, atomicity and crash-recovery identity. Keep all tasks disabled and no cleanup.

R5: independent observer validates full executable closure and source custody by stable handles after rebuild, with authenticated receipts; STOP on unknown writer, DLL resolution, task action, token, hash, parent ACL, journal or recovery state. Any rotation of previously readable secrets requires separate owner approval.

R6: only then consider a distinct, human-authorized activation decision. Offline PASS never authorizes execution, ACL Apply, cleanup, release switch or deployment.

## Severity

P0: writable SYSTEM executable closure and possible secret disclosure; physical custody unverified.
P1: unauthenticated manifests, Python DLL/import closure, existing handles, task identity and recovery trust.
P2: synthetic assertions and conservative path model; trusted signing, anti-replay and provenance infrastructure not implemented.

**Physical PC4 0/10 NOT_RUN. Execute NOT_AUTHORIZED. Cleanup NOT_AUTHORIZED. Deployment NO-GO.**
