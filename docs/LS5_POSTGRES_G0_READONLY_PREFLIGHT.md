# LS5 PostgreSQL G0 read-only inventory and G1 isolation gate

Review date 2026-10-24. This document **does not authorize** running commands on LS5, connecting to an existing database, creating roles/databases, starting Docker, or changing services. Owner must separately approve the exact G0 observation scope and any later G1. Never copy credentials, DSNs, environment variables, connection strings, query text, PGDATA contents, or service command lines into receipts.

## Exact-source inventory

PR #240: `bc8cd0c5308af3602adbd420a10cdd6e6d08f2b3` (before this document).
PR #244: `38e6ab40928cbdd6a2d6d84cbb05b4628167258f`.
PR #227: `da69209af86567232fb3038a899580fe2e061a0b`.
PR #229: `62e3e180da35fc8d6eb6c11ec1f0bf2d04f93cd7`.
PR #230: `bb224dc73bcac71aba2807b4ca85a9adca314b3d`.

## G0 — proposed owner-reviewed read-only Windows host inventory

Use an interactive PowerShell session only after authorization. Commands below inspect Windows service names/states, available command locations, listening socket metadata, and available disk space. They do **not** connect to PostgreSQL or read secrets. Avoid `Get-CimInstance Win32_Service | Select PathName`, `Get-Process | Select CommandLine`, `Get-ChildItem Env:`, `pg_settings` or `pg_hba.conf` dumps in evidence.

```powershell
$ErrorActionPreference = 'Stop'
$stamp = (Get-Date).ToUniversalTime().ToString('o')
$hostName = $env:COMPUTERNAME
$services = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue |
  Select-Object Name, Status, StartType)
$commands = @('psql.exe','pg_config.exe','pg_isready.exe','pg_dump.exe','pg_restore.exe')
$found = foreach ($name in $commands) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  [pscustomobject]@{ Command=$name; Available=[bool]$cmd }
}
$tcp = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in @(5432,55432,55439) } |
  Select-Object LocalAddress,LocalPort,State)
$disks = @(Get-PSDrive -PSProvider FileSystem |
  Select-Object Name,Free,Used)
[pscustomobject]@{
  Schema='ls5-pg-g0-readonly-1'; UTC=$stamp; Host=$hostName
  Services=$services; Tools=$found; PortListeners=$tcp; Disks=$disks
  DBConnectionAttempted=$false; PhysicalMutationAuthorized=$false
} | ConvertTo-Json -Depth 5
```

The output establishes **presence only**. Service names and ports do not prove PostgreSQL 18, schema identity, role privileges, backups, WAL health, actual DB count, or whether a listener belongs to the expected service. To inspect DB names, role grants, or server version would require a **separate expressly approved read-only DB connection** with a least-privilege inventory account and vetted SELECT-only SQL. No such authorization or credentials exist in this PR. If unavailable, record UNKNOWN, never guess.

## G1 — separate disposable test instance, not authorized on LS5

Preferred: isolated GitHub-hosted PostgreSQL 18.4 job with `tests/_pg18_database.py` attestation from PR #227 and exact-head PR #244 harness. This is **not** the LS5 production service. Alternative on LS5 requires explicit G1 approval of a dedicated isolated VM/container/port, storage root, resource budget, temporary principals, Docker context and rollback. Port availability alone is not sufficient isolation. Never use existing PGDATA, Windows PostgreSQL service, DSN or superuser. Stop on unknown custody or conflicting listener.

Proposed acceptance sequence after authorization: pin exact source; independently attest runner/container image/cluster ID; generate random DB/roles; owner-only `prepare_schema()` migrations 1–48 and schema seal; runtime app/RO negative privilege checks; verify synthetic market data/receipts; concurrent replay/rollback; isolated restart (label fast vs crash); full schema backup to custom archive, independent SHA256, restore to a *new random owned* database and compare canonical rows/catalog; verify owned process/session cleanup. A restore target is never reused, and DROP requires recorded successful creation and matching custody. Do not execute G1 commands until separately approved.

## Evidence status as of inspection

PR #240 workflow run `40083267296`: `pg18-lab` **SUCCESS**, artifact `12556183147` present; actual artifact bytes/JUnit not independently audited in this review. PR #244 workflow `40081971986`: `pg18` and four offline jobs SUCCESS, **acceptance FAILURE**; workflow overall FAILURE. PR #244 first-boot run `40081972021`: FAILURE, independent QA reports 9/26 PASS and 17/26 BLOCKED, and 32 PG JUnit cases without skips; do not treat this as whole-system GO. Physical LS5/PC4 inventory **NOT_RUN**.

## Readiness / STOP

| Area | State | Required proof |
| --- | --- | --- |
| LS5 host PostgreSQL version/service | UNKNOWN | Authorized redacted host G0 inventory, separate DB version attestation if approved |
| Schema/migrations 1–48 | CODE_REVIEWED; hosted PR244 PG job SUCCESS | Exact-head catalog/seal and complete migration receipt, independent artifact readback |
| Runtime owner/app/RO | CODE_REVIEWED; hosted PG job SUCCESS | Grants/ownership negative cases and exact-head JUnit |
| Synthetic market writes | PARTIAL | Real E2E verified rows and receipts; PR244 first boot BLOCKED |
| Crash recovery/WAL | NOT_VERIFIED | Isolated crash (not fast restart), durable post-recovery reads |
| Full Grid backup/restore | NOT_VERIFIED | Archive SHA256 + restored canonical digest/catalog |
| Physical LS5/PC4 | NOT_RUN / NO-GO | Separate owner G1 authorization and physical evidence |

P0: owner authorization boundary, physical inventory UNKNOWN, integrated E2E BLOCKED. P1: independent PG artifacts, crash recovery, Grid restore, pending writes. P2: RPO/RTO/retention. **Physical GO is prohibited.**
