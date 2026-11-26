# Pure Data history v1.2 implementation plan

Approved parent map supersedes proposal version names. Base 25f80cf239e76543e5968a472d8b9cfe467d4794; no publication.

- Add tests/market_data/test_history_snapshot_v12.py: actual Trade→FootprintBuilder→minute_record_v12 fixtures, fake read-only cursors, exact minutes/window/multipin/series selection.v1.2. Watch missing-function RED before production code.
- Add market_data/history_snapshot_v12.py: closed discriminated selection policy; strict catalog-entry.v1.2 (new digest IDs), existing request.v1.2/trust.v1.2/receipt.v1.2; full envelope checks; shared rollup.v1.2 retaining actual turnover, explicit units/basis/encoding/availability and ordered parents. No response/endpoint implementation.
- Refactor numeric_dto.amount_total as sole Math.exact_sum normalization helper; volume_total delegates. Extend existing history_snapshot._candle with explicit closed version policy, retaining old default bytes; new projection shares it.
- Tests pin delayed middle availability900000 and actual turnovers200..204→1010, ordered pages/gaps/units/basis/receipt/context/overflow/callback/full-future-domain refusal; old export/catalog/rollup goldens unchanged.
- Append mandatory node IDs; preserve original547 ledger and516 counter. Archive numeric_dto/history_snapshot original baseline blobs from original ledger revision. Freeze runtime commit first; metadata-only current47+newmodule sidecar/census update anchors that immutable commit, never self-reference.
- Run reviewed denied-effects source and extracted-wheel suites on Python3.11/3.12; mandatory roster/package guards. Full local suite forbidden by SAFE_CODE_ONLY/native boundary. Record exact SHA and independent-review handoff, unpublished NO_GO.
