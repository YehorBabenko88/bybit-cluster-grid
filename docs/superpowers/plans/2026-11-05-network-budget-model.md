# LAB Network Budget Model Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to execute these
> bounded tasks inline. Root reviews the shared contract before integration.

**Goal:** Prove conservative network scheduling invariants with a deterministic
six-node, ten-symbol model without performing network or physical I/O.

**Architecture:** One serialized cluster meter reuses the future existing Grid
CONTROL transaction boundary. Closed actor operations derive priority. Bounded
pending tickets and unresolved transfer permits are network state, not Grid job
ownership. The model does not claim actual persistence or authentication.

**Tech Stack:** Python standard library, pytest; no new dependencies.

**Spec:** `docs/network-budget-lab-contract.md`.

## Task 1 â€” metering and replay invariants

- [x] Write failing tests for cold start, exact integer refill, byte envelopes,
  restart/no new burst, rollback and idempotency.
- [x] Observe RED, implement `grid/network_budget_model.py`, verify GREEN.
- [x] Record which persisted-state and actor inputs are synthetic models.

## Task 2 â€” concurrency, pressure and outage

- [x] Write failing tests for two unresolved bulk permits, no expiry reuse,
  priority/capacity/backpressure, Bybit cooldown and paced HTTP/WS attempts.
- [x] Implement minimal transitions; verify all tests with no network calls.
- [x] Test degradation hysteresis and explicit cold recovery after LS5 outage.

## Task 3 â€” six-node/ten-symbol simulation and review

- [x] Add deterministic simulator and tests for simultaneous history/live,
  latency/loss, authority outage, Bybit outage, module restart and recovery.
- [x] Export a machine-readable synthetic report with per-phase bounds.
- [ ] Root reviews contract, limitations and actual test evidence before a
  source-only Draft PR and before any SQL/API/ingestion integration.
