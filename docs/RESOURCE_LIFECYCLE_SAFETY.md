# Resource and lifecycle safety

Grid workers are intentionally bounded and disposable.

- Worker and Strattester child-process memory budgets are configurable. New compute work is
  not claimed under system resource pressure, and an over-budget Strattester process tree is terminated.
- Temporary research/archive directories are service-owned and periodically removed after their TTL.
  Cleanup never recursively deletes arbitrary user directories.
- The content-addressed cache is SHA-256 verified, size bounded and age bounded.
- PostgreSQL market-data retention remains watermark/hold protected and fails closed when consumers
  have not confirmed safe deletion.
- Terminal scheduler rows are retained for a bounded audit window and then cleaned in batches.
- Worker lifecycle is ONLINE -> OFFLINE -> QUARANTINED -> DECOMMISSIONED. OFFLINE compute leases
  expire for reassignment. A heartbeat restores OFFLINE/QUARANTINED nodes, but a DECOMMISSIONED
  node requires explicit re-enrollment.
- Windows service recovery covers crashes and reboots. Files are protected from routine non-admin
  modification, while SYSTEM/Administrators retain normal stop/update/uninstall control.
- The agent never tries to become undeletable and never self-deletes installed program files merely
  because the network was unavailable. Long-term absence revokes cluster participation instead.

This design protects reproducibility and disk/RAM health without creating hostile persistence.
