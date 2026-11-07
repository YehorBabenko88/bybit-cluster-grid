# Offline Gateway Query Preparation Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement task by task.

**Goal:** Validate closed bounded synthetic OHLCV requests without executing reads.
**Architecture:** One pure stdlib module; immutable canonical query bytes and a
separate denial result. No store/authority dependencies or shared ABI wiring.
**Tech stack:** Python3.12, unittest/pytest in the existing isolated test venv.
**Spec:** Agent3 outputs/gateway-query-api-review1.md plus Root direction ACK:
pure preparation allowed; exact shared ABI and A2/A4 disclosure remain pending.

## Constraints and review focus

Only grid/gateway_query.py, tests/gateway_query/**, docs/gateway/query/** and own
optional workflow may change. No IO, actual execution or grants. Unknown profile,
identity, unsafe range, missing cut/context and noncanonical inputs reject. Digest
agreement does not prove registry/coverage/publication. Financial values are not
parsed or inferred. No latest fallback, L3/book capability or fake empty history.

## Task 1 — Pure preparation and explicit denial

- [x] Add tests/gateway_query/test_preparation.py; verify missing module RED.
- [x] Implement only grid/gateway_query.py: bounded canonical bytes validation,
  fixed synthetic linear/1m profile, exact instrument and typed cuts/context,
  immutable PreparedQuery and detached NOT_EXECUTED result with rows=null.
- [x] Run own tests. Exercise malformed/deep/duplicate/noncanonical/numeric input,
  UUID/u63/hash grammar, cross-market/profile mismatch, empty/excessive/unaligned
  range, unavailable old cut, future candle range, missing context, detached views,
  hostile forged local objects and denial with IO hooks disabled.
- [x] Record exact local profile/schema bytes, scope/limits and explicit no-ACK
  runtime boundary in docs/gateway/query/preparation.md.
- [x] Review source diff, tests and isolation; no shared API or positive adapter.

## Deferred tasks

Actual A2 opaque READ_DATA capability/current-session checks and A4 exact bounded
store/manifest/row contract must receive pairwise ACK before adapters or positive
synthetic query execution. Workflow and durable fixture/reopen tests follow that
separate admission. No hosted PASS or synthetic/native acceptance transferred.

Rollback: remove new files only; no data touched.
