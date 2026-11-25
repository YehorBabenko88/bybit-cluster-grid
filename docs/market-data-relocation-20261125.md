# market_data relocation: strattester → Grid (Workstream B1, MASTER unified-system#111)

Owner decision 2026-11-25: Grid is the single owner of all Bybit interaction and market data.

Source: `YehorBabenko88/strattester@3850995a6c28ed29b05cef4ba067e587d5033453` (Data PR #121).
Base: `YehorBabenko88/bybit-cluster-grid@c9ffdaa2af52c4d55871a48655a77a0c669da80f` (Grid PR #295).

## Byte-identical from strattester (git archive of the source commit)
`pyproject.toml`, `MANIFEST.in`, `README.md`, `market_data/`, `scripts/` (17 custody/roster scripts),
`tests/market_data/`, `tests/unmigrated_market_data/`, `integration_tests/`, `docs/market-data-consolidation.md`,
and the five roster files of `tests/marketdata/` (audit, coverage, history_plan, readiness, rich_sync).
Workflow `market-data-pure.yml` is verbatim. `market-data-tests.yml` = strattester `tests.yml`, except
the pytest step runs the exact 902-node roster instead of the whole legacy strattester suite.

Not relocated: legacy `strattester/` package and the legacy-only nodes in `tests/marketdata/*`
(they import `strattester.marketdata` and are not in the 902 roster).

## Grid files moved (not deleted)
- `README.md` → `docs/legacy/grid-README.md`
- `pyproject.toml`, `setup.py`, `MANIFEST.in`, `market-wheel-modules.txt` → `legacy/grid-market-wheel/`
  (legacy 11-module `unified-grid-market-data` wheel, superseded by `market-data`; its evidence workflow
  now builds from a staged copy and stays green until an explicit retirement PR).
- Broad `pytest` runs in `preflight.yml` / `mission3-qualification.yml` ignore the relocated
  market-data test directories, which have their own strict lanes.

## Equivalence evidence (local, setuptools 84, SOURCE_DATE_EPOCH=315532800)
Wheel: 54 members, every member sha256 identical between strattester@3850995 and this branch.
Sdist: every member sha256 identical. Archive bytes differ only by local builder metadata;
the pinned-builder evidence is produced by `market-data-pure.yml` in CI.

## Not done here (next PRs)
B2 Root cohort switch (`integration/four_owner/cohort.json` market_data.repository → Grid).
B3 continuous WebSocket / L2 / ticker / OI from legacy `grid/` into `market_data`, each with an
equivalence test. B4 removal of the 52 Grid↔market_data duplicate groups after B3.
B5 strattester: mark `market_data` there as moved (no deletion before Root switches).
Release status: NO_GO.
