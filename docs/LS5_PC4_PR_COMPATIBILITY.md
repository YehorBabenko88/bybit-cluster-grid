# LS5/PC4 source compatibility watch

This is source-level risk assessment, not a merge, integration acceptance or physical
observation. Baseline was read directly from GitHub; source blobs are fetched by
immutable object ID, checked against Git blob identity and SHA256. A final HEAD
recheck marks an advancing PR incomplete. No source branch is modified.

| PR | Observed exact HEAD | Stable during collection |
|---|---|---|
| #238 | `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149` | True |
| #239 | `0dd0cea71f9fd8105deaefc6cfccc0dfe793a689` | True |
| #240 | `bc8cd0c5308af3602adbd420a10cdd6e6d08f2b3` | True |
| #241 | `152be6404d4764ec1bba041c679a5719746e8dbc` | True |
| #242 | `d5966963e6671fe3377dcfe408a78f4a20b70f33` | True |
| #244 | `38e6ab40928cbdd6a2d6d84cbb05b4628167258f` | True |

Per-PR full SHA256 and interface fingerprints for every selected file are in
`planning/physical-first-boot/compatibility-matrix.json`; `pr-baseline.json` preserves
the replayable input. Null means absent, never a matching empty file. Metadata was
captured before the new physical-planning commit; PR244 HEAD drift is expected after
publication and must be reviewed. Do not relabel that snapshot as the final HEAD.

| File | Comparison | Priority | Component owners to review |
|---|---|---|---|
| `.github/workflows/ls5-native-observer.yml` | DIVERGENT_OR_ABSENT | P1 review | #238, #244 |
| `.github/workflows/ls5-network-offline.yml` | DIVERGENT_OR_ABSENT | P1 review | #241, #244 |
| `.github/workflows/ls5-physical-acceptance-offline.yml` | DIVERGENT_OR_ABSENT | P1 review | #242, #244 |
| `.github/workflows/ls5-postgres-readiness-offline.yml` | DIVERGENT_OR_ABSENT | P1 review | #240, #244 |
| `.github/workflows/ls5-postgres18-disposable.yml` | DIVERGENT_OR_ABSENT | P1 review | #240, #244 |
| `.github/workflows/ls5-trusted-bootstrap-offline.yml` | DIVERGENT_OR_ABSENT | P1 review | #239, #244 |
| `.gitignore` | DIVERGENT_OR_ABSENT | P2 review | #238, #239, #240, #241, #242, #244 |
| `docs/ISOLATED_AGENT_NETWORK_CONTRACT.md` | DIVERGENT_OR_ABSENT | P2 review | #241, #244 |
| `docs/LS5_CODEX_ISOLATED_WINDOWS_BOOTSTRAP.md` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `docs/LS5_E2E_INDEPENDENT_ACCEPTANCE.md` | DIVERGENT_OR_ABSENT | P2 review | #242, #244 |
| `docs/LS5_NETWORK_READINESS.md` | DIVERGENT_OR_ABSENT | P2 review | #241, #244 |
| `docs/LS5_PG18_CODEX_DISPOSABLE_CONTRACT.md` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `docs/LS5_PHYSICAL_ACCEPTANCE_MATRIX.md` | DIVERGENT_OR_ABSENT | P2 review | #242, #244 |
| `docs/LS5_POSTGRES_18_READINESS.md` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `docs/LS5_TRUSTED_BOOTSTRAP.md` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `docs/LS5_TRUSTED_SOURCE_HANDOFF.md` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `grid/config.py` | IDENTICAL | P2 review | #238, #239, #240, #241, #242, #244 |
| `grid/coordinator.py` | DIVERGENT_OR_ABSENT | P1 review | #238, #239, #240, #241, #242, #244 |
| `grid/migrations.py` | IDENTICAL | P2 review | #238, #239, #240, #241, #242, #244 |
| `grid/schema_contract.py` | DIVERGENT_OR_ABSENT | P1 review | #244 |
| `grid/schema_preparation.py` | DIVERGENT_OR_ABSENT | P1 review | #244 |
| `grid/worker.py` | DIVERGENT_OR_ABSENT | P1 review | #238, #239, #240, #241, #242, #244 |
| `installer/ls5_bootstrap_ci_evidence.py` | DIVERGENT_OR_ABSENT | P1 review | #239, #244 |
| `installer/ls5_disposable_release_model.py` | DIVERGENT_OR_ABSENT | P1 review | #239, #244 |
| `installer/ls5_e2e_acceptance.py` | DIVERGENT_OR_ABSENT | P1 review | #242, #244 |
| `installer/ls5_network_offline.py` | DIVERGENT_OR_ABSENT | P1 review | #241, #244 |
| `installer/ls5_pg_readiness.py` | DIVERGENT_OR_ABSENT | P1 review | #240, #244 |
| `installer/ls5_physical_acceptance.py` | DIVERGENT_OR_ABSENT | P1 review | #242, #244 |
| `installer/release-runtime-guard.ps1` | IDENTICAL | P2 review | #238, #239, #240, #241, #242, #244 |
| `installer/trusted_bootstrap.py` | DIVERGENT_OR_ABSENT | P1 review | #239, #244 |
| `installer/windows_preflight.py` | IDENTICAL | P2 review | #238, #239, #240, #241, #242, #244 |
| `requirements.txt` | IDENTICAL | P2 review | #238, #239, #240, #241, #242, #244 |
| `tests/test_ls5_bootstrap_ci_evidence.py` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `tests/test_ls5_disposable_release_model.py` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `tests/test_ls5_e2e_acceptance.py` | DIVERGENT_OR_ABSENT | P2 review | #242, #244 |
| `tests/test_ls5_network_offline.py` | DIVERGENT_OR_ABSENT | P2 review | #241, #244 |
| `tests/test_ls5_pg18_disposable.py` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `tests/test_ls5_pg18_restore.py` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `tests/test_ls5_pg_evidence_integrity.py` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `tests/test_ls5_pg_readiness.py` | DIVERGENT_OR_ABSENT | P2 review | #240, #244 |
| `tests/test_ls5_physical_acceptance.py` | DIVERGENT_OR_ABSENT | P2 review | #242, #244 |
| `tests/test_ls5_trusted_bootstrap.py` | DIVERGENT_OR_ABSENT | P2 review | #239, #244 |
| `tools/collect_ls5_network_readonly.ps1` | DIVERGENT_OR_ABSENT | P2 review | #241, #244 |

## Concrete integration boundaries

- PR238/native owner: observer handles/parent security identities/TOCTOU and fixture
  contracts; production Apply/Rollback stays blocked. Integration only adds reusable
  workflow invocation and a concurrency namespace, not a new physical authority.
- PR239/bootstrap owner: staging model is synthetic, not secure executable custody;
  oversized Windows pytest IDs require bounded IDs (fixed only in integration).
- PR240/PG owner: older profile trees omit grid/schema_contract.py and
  grid/schema_preparation.py; PG16-only physical tooling cannot commission PG18.
  Exact source digest/seal must be regenerated by separate preparation in a new cluster.
- PR241/network owner: offline validator fixes known historical IPs and port55432;
  these are NOT current host observations. New physical profile requires fresh routes,
  SSH identity approval and new nonreserved ports; old policy is not weakened.
- PR242/acceptance owner: imported baseline SHA regex/signature/duplicate test defects
  were independently reproduced in integration; newer branch changes require its own
  tests. Its evidence schema is not our26-stage E2E receipt; no adapter may invent PASS.
- PR244/integration owner: real DB-less heartbeat and endpoint fixes are not present
  in older component trees. `run_coordinator.py` wildcard bind is unsuitable for the
  proposed physical loopback profile. No physical executor exists in this change.

Same SHA256 proves identical source bytes only. Function-argument/return/decorator
AST fingerprints detect simple interface drift but cannot establish auth, ABI, SQL
or semantic compatibility. Requirements and manifests require separate reviews.
Divergence is a review risk, not automatically a demonstrated P1 defect. Documentation
absence is P2 review. Existing source-level regression tests remain evidence only for
those cases, not for unexecuted Windows/PG18 integration.

## Reproduction (GitHub reads only)

```powershell
& $TrustedPython -m integration.pr_compatibility
# PLAN_ONLY, no network
& $TrustedPython -m integration.pr_compatibility --collect-github --baseline planning/physical-first-boot/pr-baseline.json
```

The collector reads PR files/trees/blobs and exact-head Actions/artifact metadata.
It never downloads/extracts executable artifacts, executes fetched code, writes refs,
merges or changes policy. Redirect stdout only to a new owner-controlled evidence file.
Transport exit0 means a report was produced, NOT CI success or compatibility. Read
`metadata_valid`, `ci_all_success`, `head_drift`, `overlaps`, and missing artifact gates.
Latest run per required workflow wins; queued/skipped/newer failed runs cannot reuse
an older success. Missing required workflows/artifacts remain BLOCKED. Artifact metadata
is not byte verification. CI does not get GitHub-write permissions or schedule merges.
