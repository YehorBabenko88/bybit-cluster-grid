# Distributed acceptance gate

This gate is required before enabling distributed research or archive compute in production.

## Automated contract

Run:

```powershell
python -m pytest -q tests/test_distributed_acceptance_contract.py tests/test_distributed_determinism.py tests/test_archive_compute_materializer.py
```

It verifies content-addressed dataset materialization, deterministic shard aggregation,
archive artifact round-trip, pre-write validation, and stale-generation fencing.

## Physical multi-PC acceptance

Use one CONTROL and at least two COMPUTE nodes. All machines must run the same Grid
revision and the same configured Strattester version.

1. Export one small frozen dataset with `POST /research/datasets/export`.
2. Create a backtest with at least two symbols and two strategies using
   `POST /research/backtests`.
3. Confirm different nodes claim different shards and that every worker obtains the
   exact dataset SHA-256 advertised by CONTROL.
4. During one running shard, stop the worker service or disconnect that computer.
   Do not modify PostgreSQL manually.
5. Wait for its lease to expire and confirm CONTROL reassigns the work with a higher
   `lease_generation`.
6. Reconnect the old node. Its late result must receive a conflict/fencing response
   and must not change the completed shard.
7. Confirm the run reaches COMPLETE, exposes a `research_result` artifact, and its
   aggregate fingerprint is identical to a single-node run over the same frozen dataset.
8. Repeat with one archive compute job. Disconnect the worker after computation but
   before result acknowledgement. The exact same result may be replayed; a conflicting
   result hash must be rejected.
9. Restart CONTROL while work is leased. After restart, expired leases must be
   recovered and no job may have two accepted owners.
10. Record worker RSS, cache size and PostgreSQL size before and after repeated runs.
    After retention/maintenance, service-owned temporary workspaces must disappear and
    cache/database growth must plateau rather than grow linearly.

## Pass criteria

- No duplicate accepted shard or archive result.
- No stale generation can commit.
- Distributed and single-node aggregate fingerprints match.
- Corrupt/mismatched artifacts are rejected before canonical PostgreSQL writes.
- Live workload resource guards remain effective while research runs.
- Worker restart, CONTROL restart and network loss recover without manual database repair.
- Administrators can still stop, update and uninstall the service normally.

Do not enable real trading as part of this gate. Shadow/simulation remains the next
promotion stage after this acceptance passes.
