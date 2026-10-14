# MIGRATION48_CODEX_REPORT

Дата:2026-10-14. Только локальная подготовка к ревью; никаких push/PR/merge/deployment и запусков SQL на PostgreSQL.

Исходный SHA: `15dd80674e326e6efd414d649288762adad7e12a`.
Локальная ветка: `audit/codex-migration48-review-20261014`.
Worktree: `C:/Users/LS-5/Documents/Codex/2026-10-13/codex-bybit-cluster-grid-yehorbabenko88-bybit/work/migration48`.
Изменения не закоммичены. HEAD остаётся исходным SHA; отдельного SHA коммита кандидата нет. Подготовлен экспортируемый patch для дальнейшего ревью.

## База и отсутствие дубликата

Актуальные Git refs получены read-only fetch; GitHub API проверен read-only. [main](https://github.com/YehorBabenko88/bybit-cluster-grid/tree/main) — `d537d525296ef34f727996e240ae6c60102c6082`, максимум46. [PR172](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/172) — `6839f46031dd7fa8ebc0bec9771564abb56b0267`, максимум47; он предок исходного кандидата. [PR184](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/184) — `15dd80674e326e6efd414d649288762adad7e12a`, максимум47, Draft/unmerged. Базировать48 прямо на main нельзя: потеряется зависимость47 и её collection_ownership.

Проверенная stacked-цепочка:172 →173 `fe9f3f09dd4f950663c2cb782d30da3067546d5a` →180 `a79ee1234b082f84dae9226a0b8cdfa0025a0249` →181 `061e28c6b3062a545997b319a05870b07d164f63` →182 `b18a9d7969e61b2f17b6c57541050cd6a6ec82ec` →183 `f6047276b9be3caad190b4f68ee7945d11641b42` →184. В180 уже составлены изменения174–179. Эти PR и ветки не изменялись.

В201 полученном remote-ref просмотрен grid/migrations.py: регистрации48 и имени model_registry_dataset_lookup_index не найдено. Новые remote-ветки audit/rollback-preflight-under-mutex-20261014 и audit/rollback-preflight-mutex-20261014-2240 тоже указывают на исходный15dd806 и не содержат48. Проверка ограничена доступными полученными refs, не чужими локальными/unpublished патчами.

## Входной патч

Файл `C:/Users/LS-5/GridCommissioning/migration48-review/migration-48-model-registry-index.patch` только прочитан. SHA256 точно совпал:
`6685cf7542530c0d38aaa3e5ba06686236ac3e5a4699c9784fea69c1d53afa49`.
`git apply --check` прошёл. AST/literal сравнение добавляемого tuple с локальным MIGRATIONS[-1] подтвердило точное совпадение версии, имени и SQL. Сохранено `ON public.model_registry(dataset_id)`, без CONCURRENTLY и без изменения исторических миграций.

## Catalogue and commissioning contract

validate_legacy_catalogue accepts the historical1–34 source only against reviewed
current1–47 or exact known1–48. Tests cover both current catalogues, historical SQL
changes, unknown48/49, invalid names and corrupted release manifests. An initial
regression reproduced failure of historical34 validation with current48 before fixing
that narrow allowlist. Historical manifests/fixtures are unchanged. Legacy database
approval remains exactly47; modern commissioning requires48 and its physical index.
The supplied migration tuple and historical migrations retain their SQL unchanged.

## Complete changed file inventory

- .github/workflows/preflight.yml
- docs/MIGRATION48_CODEX_REPORT.md
- docs/MIGRATION48_RECOVERY_RUNBOOK.md
- grid/migration48_index.py
- grid/migrations.py
- installer/tests/legacy_rollback_driver.py
- installer/tests/test-built-bundle.ps1
- installer/tests/test-legacy-rollback.ps1
- installer/windows_preflight.py
- tests/_postgres_test_database.py
- tests/test_collection_ownership_postgres.py
- tests/test_disposable_cluster_attestation.py
- tests/test_legacy_rollback_preflight.py
- tests/test_migration47_upgrade_postgres.py
- tests/test_migration48.py
- tests/test_migration48_postgres.py
- tests/test_windows_preflight_postgres.py

## Remaining risks

CREATE INDEX may block writes; production duration/lock contention is unmeasured.
Seventeen real SQL cases and the actual hosted Docker CI service have not run. Existing
corrupt ledger48/index states require separate authorized repair; no automatic rebuild.
Legacy recovery to an incompatible historical pointer is not permission to start it.
No production HA or deployment readiness claim is made. actionlint, diff whitespace
validation and Windows PowerShell5.1 parser passed. New Python files compile.

## Review fixes and verification (2026-10-14)

All changes are local and uncommitted in audit/codex-migration48-review-20261014.

Tests were added before fixes. Wrong existing index initially reproduced an erroneous
ledger48 insertion; the runner now calls shared grid/migration48_index.py inside the
migration transaction before recording48 and on replay. It rejects invalid/wrong,
partial/expression/unique/include/non-btree indexes and accepts a correct existing
index without rebuilding it. Original migration tuple, advisory lock and SQL transaction
remain intact. Seventeen real PostgreSQL cases are prepared but were NOT executed.

The disposable-database helper now requires the exact current GitHub-hosted Linux
repository/job/run service container, run-bound labels, local default Docker context,
postgres:16, matching port, explicit tmpfs data mount, unambiguous PGDATA, no nested
mounts and container-local SHOW data_directory. Before CREATE it compares the
container system_identifier with a read-only host connection. Provider failures are
redacted and fail closed. These checks trust the hosted runner/local Docker daemon;
they are not cryptographic proof against a compromised runner administrator.

New tests/test_disposable_cluster_attestation.py mocks ALL Docker/asyncpg operations.
Three further review cases (alternate PGDATA, nested persistent mount, effective
configuration mismatch) first failed (3 failed/15 passed), then passed after correction.
The independent static reviewer found this P2 and no other concrete P1/P2; that review
preceded the final PGDATA fix. No real Docker or PostgreSQL test was executed.

Final offline Python suite: 1291 passed,46 skipped,7 subtests; four existing FastAPI
warnings. Five PG-only modules excluded; POSTGRES_DSN and CI opt-in unset.
A preliminary targeted run had10 setup errors from inaccessible system TEMP;
full verification uses workspace TEMP. PowerShell5.1 and7 each passed52 LegacyRollback,
195 Runtime Guard and10 packaging cases with synthetic providers. New16 legacy cases
cover schema48 plan/apply, prepared/committed recovery, repeated recovery, rejection
on retry and preserved pending-marker refusal for both historical SHAs and roles.

Additional/changed follow-up files:
- grid/migration48_index.py: shared strict index metadata validator.
- grid/migrations.py: transactional index postcondition and replay validation.
- installer/windows_preflight.py: reuse shared validator.
- tests/_postgres_test_database.py: fail-closed current-run ephemeral CI proof.
- tests/test_disposable_cluster_attestation.py: negative/positive provider mocks.
- tests/test_migration48.py and tests/test_migration48_postgres.py: index regressions.
- .github/workflows/preflight.yml: local CI service labels/tmpfs/container binding.
- installer/tests/legacy_rollback_driver.py and test-legacy-rollback.ps1: schema48 matrix.
- installer/tests/test-built-bundle.ps1: updated52-case count.
- docs/MIGRATION48_RECOVERY_RUNBOOK.md: recovery plan and blocked cases.

See MIGRATION48_RECOVERY_RUNBOOK.md. Database48 cannot pass LegacyRollback47.
Never delete ledger48, downgrade, weaken fencing or edit historical manifests.
Committed recovery can preserve pending.version and block another switch; a separately
reviewed offline pointer repair plan/tool is required. No automated safe exit is claimed.
Prepared/committed file recovery does not authorize activation of an historical runtime.

HEAD remains15dd80674e326e6efd414d649288762adad7e12a; no new commit/push/PR/merge,
deployment, production service/database/release changes or GitHub calls in this follow-up.
Actions and real PostgreSQL/Docker validation remain pending separate authorization.
Ready for local review only, not deployment. Exact patch checksum is in the exported
report/metadata to avoid a self-referential hash inside this patch.


## Stage 116M-13V — final local index-definition audit

Scope: local branch only; HEAD15dd80674e326e6efd414d649288762adad7e12a.
This stage changes grid/migration48_index.py, tests/test_migration48.py,
tests/test_migration48_postgres.py and this report. The exported patch is cumulative
against HEAD and includes the prior local migration48/legacy/CI fixes listed above.

### Reproduced defect and correction

P2: a same-name index with different operator class, sort/null order or other
unexamined definition metadata could pass the previous validator and register48.
Before changing the validator,45 offline regressions failed as expected:15 definition
variants exercised unregistered48, replay of recorded48, and modern commissioning.
All45 pass after the fix. The query-aware catalogue double projects only SELECTed
fields, reproducing omitted metadata checks; it does not execute SQL or prove that
PostgreSQL accepts the query. Actual DDL regressions remain pending CI.

The shared read-only validator now requires:
- the built-in pg_catalog.uuid_ops identity for btree/UUID, resolved by catalogue OID,
  not an unqualified opclass name; a public.uuid_ops impostor is rejected;
- UUID type in both table and index key, zero collation OID (UUID is noncollatable);
- indoption0, meaning ASC/NULLS LAST; all other bit patterns fail closed;
- no explicit opclass attribute options or relation storage options;
- ordinary persistent table/index objects, no primary/exclusion constraint identity
  or NULLS NOT DISTINCT override;
- all previous validity, readiness, liveness, nonunique, column count, no INCLUDE,
  no expressions/predicate, relation identity and access-method requirements.

Explicit uuid_ops/ASC/NULLS LAST syntax normalizes to the same catalogue definition
and is accepted. Explicit WITH options, even default-valued ones, are conservatively
rejected because the reviewed DDL specifies none. Tablespace placement, owner,
statistics, CLUSTER history and transient indcheckxmin are not lookup-definition
comparisons. Tablespace selection can depend on session defaults; this validator is
not a storage-placement or database-administrator tamper audit.

References consulted read-only:
- https://www.postgresql.org/docs/16/catalog-pg-index.html
- https://www.postgresql.org/docs/16/catalog-pg-opclass.html
- https://www.postgresql.org/docs/16/catalog-pg-attribute.html
- https://www.postgresql.org/docs/16/sql-createindex.html
- https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/include/catalog/pg_index.h

### Preserved contracts

The original migration48 SQL tuple is unchanged. The runner still checks the shared
validator within the existing transaction before ledger INSERT, releases its existing
advisory lock in finally, and validates recorded48 on replay. Regression tests assert
no new ledger entry and lock release for every mismatch. Modern commissioning imports
the very same function (identity asserted), runs read-only, and blocks the same cases.
LegacyRollback schema47 approval, historical1–34 validation, unknown catalogue rejection,
manifest checks and fencing have not been widened.

### Verification and CI readiness

Python3.12.14 offline:1291 passed,46 skipped,7 subtests; four pre-existing FastAPI warnings.
The five PostgreSQL-only modules named in the previous run command remain excluded;
POSTGRES_DSN and GRID_DISPOSABLE_POSTGRES_TESTS are unset for offline verification.
Seventeen cases in tests/test_migration48_postgres.py are collected but skipped,
including11 new cases: three sort/null orders, custom same-name UUID opclass,
fillfactor, deduplication, INCLUDE, predicate, expression, collated text schema drift,
and positive explicit-equivalent defaults. No system-catalogue mutation is used.

Windows PowerShell5.1.26100.9711 and7.6.5: each passed52 LegacyRollback,195 Runtime Guard and10 packaging cases; providers synthetic, fixture files only.
PowerShell5.1 parser, Python compileall, actionlint and git diff --check pass.
The PostgreSQL workflow was parsed and checked: ubuntu-latest postgres:16 service,
tmpfs/run labels, exact service-container ID binding before pytest, explicit CI opt-in,
correct DSN, migration48 SQL step, and all original named gates retained. Workflow
configuration was not changed in this stage. Windows bundle recursively packages grid,
including the shared validator; manifest generation remains unchanged.

Ready to submit this exact candidate for separately authorized isolated GitHub Actions
validation. This is permission readiness, not an Actions PASS: nothing was pushed and
no workflow dispatched. Real SQL syntax/catalogue behavior, transaction/concurrency
cases and actual Docker attestation still need that execution. No production readiness
claim. Recovery constraints in MIGRATION48_RECOVERY_RUNBOOK.md remain applicable.
