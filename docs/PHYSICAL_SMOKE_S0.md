# Physical public smoke S0 — operator runbook

Status: **BLOCKED pending independent review, owner authorization and complete G0**. This document authorizes no physical execution, staging, transfer, configuration change or cleanup. No physical smoke result is established by source tests or hosted CI.

Read-only G0 on 2026-10-28 recorded **LS5 / LS5\\LS-5 / 100.103.160.110**. A previous narrative incorrectly called that host PC5; the original unchanged JSON with SHA256 `e1d8cba9190abb464512830ccdcbb98dbc2e081de2a2baedfc6d6074b7089eab` actually says LS5. Independent revalidation through managed machine identity, native hostname/whoami, CIM and Tailscale agrees with the owner's observations. The PC5 claim is withdrawn; it must never be used as evidence. PC4 SSH operator has enabled Administrators membership, so a standard operator token remains required; do not relax checks or alter accounts. Port 49441 was unoccupied at the original observation, which is not a reservation. Full host identifiers remain in private G0 evidence outside Git. No S0 process was started, and staging/start remain NOT_AUTHORIZED.

S0 is a standalone, short public-data experiment: a Coordinator on LS5 accepts PC4 registration, heartbeats and one assignment; a Worker on PC4 collects `BTCUSDT` public order book and trade messages from `wss://stream.bybit.com/v5/public/linear`. It does not start the production Grid entrypoints, database, trading clients or services. In particular, the old Coordinator startup that initializes the full database is never used; this S0 adapter exercises only a partial public-data path. It does not demonstrate full Grid operation, high availability, failover, production readiness or a G1 sandbox. All twenty G1 gates remain **BLOCKED**. S0 has separate human authorization; no manifest authority flag is promoted.

Hosted Bybit observations confirmed that a public topic may precede the subscribe ACK. A shared pure handshake gate freezes at most eight exact-topic frames / 2 MiB for at most two seconds. No counters or market journal records are accepted before a valid `success=true`, `req_id=S0` subscribe ACK releases them in arrival order. Missing/rejected/duplicate ACK, private/unknown topics, clock regression and overflow stop the run. Every reconnect uses a fresh handshake gate. Hosted synthetic fixtures reproduce this ordering, including after reconnect; public diagnostics do not bypass the same gate.

## Boundaries

The portable artifact contains CPython 3.12 console Python, bounded standard library, the reviewed public WebSocket/TLS dependency closure, S0 modules, wrapper, `installer/physical-smoke-s0/S0Launcher.cs`, hosted-compiled `native/S0Launcher.dll`, and this runbook. The wrapper loads the DLL from bytes after checking its digest against the original SHA-pinned ZIP manifest and matching the extracted manifest. It never compiles code on a physical machine. It contains no operator configuration, private keys, certificates, credentials or actual host pins. Only `subscribe` for `orderbook.1.BTCUSDT` and `publicTrade.BTCUSDT`, and `ping`, are allowed Bybit operations. No private/trade endpoint or authenticated exchange operation is in scope.

Python runs foreground with `-I -S -B`; there is no service installation, scheduled task, background daemon or production process launch. The wrapper's original-package-pinned native launcher starts only its bundled Python suspended, assigns it atomically to its own kill-on-close Windows Job with active-process limit one, checks the actual parent primary token and created child token (SID, elevation, enabled Administrators group and medium integrity), validates the owned process identity and image, then resumes it. The hosted fixture records the observed token facts; these checks are requirements, not a claim that any physical token has already been observed. Execute has a kernel-enforced budget of at most 300 seconds; other actions have 60 seconds. Python's self watchdog is a backstop. Closing the launcher's own Job on timeout or parent exit terminates only its owned child. The Worker receives only the Coordinator's remaining window. `PUBLIC_SMOKE_OBSERVED` requires both role evidence sets and at least 240 seconds of actual healthy collection, not merely elapsed process time. Operator stop or an incomplete window produces `PARTIAL`, not a pass.

The trust boundary includes the authorized operator, Windows and administrators. The native Job bounds only the owned process lifetime/count; it uses the normal standard token and is not AppContainer or G1. Application allowlists, import checks and route observations do not prove complete OS network containment and do not defend against a malicious local administrator. There are no firewall repairs, ACL rewrites on existing objects, account changes, DB changes, PID kills or automatic cleanup.

## G0: owner supplies and independently reviews

Before preparation, record the following in a private owner review record. Do not substitute example values from tests.

| Input | Required evidence | Otherwise |
|---|---|---|
| Source | Reviewed exact 40 character Git HEAD and tree, independent review outcome | BLOCKED |
| Package | Future hosted `s0-windows` run/attempt, receipt, ZIP SHA256, complete matching manifest and source pins | BLOCKED |
| Machines | Logical LS5 / PC4 roles mapped to exact uppercase Windows GetComputerNameW NetBIOS names in `hostnames`; distinct approved literal private/CGNAT IPv4 addresses and usable approved high port | BLOCKED |
| Operators | Full, distinct LS5 and PC4 operator SIDs, actual token evidence | BLOCKED |
| Token | Unelevated medium token, Administrators group not enabled; only enabled privilege `SeChangeNotifyPrivilege` | BLOCKED |
| Custody | Existing trusted parent and protected package root on each machine; package root protected DACL with exactly three explicit Full Control ACEs: SYSTEM, BUILTIN Administrators, that machine's operator | BLOCKED |
| Transfer | Separately approved encrypted verified SSH channel, full verified host fingerprint, source/destination identity and custody | BLOCKED |
| Network | Approved interfaces/routes/Tailscale state, correct local bind IP, no conflicting port | BLOCKED |
| Authorization | Explicit standalone S0 preparation/execution authorization and independent review complete | BLOCKED |

The optional hosted-only `tools/probe_s0_public_ci.py` diagnostic uses the fixed public Bybit endpoint for at most ten seconds without credentials. `BLOCKED` or `OBSERVED_PUBLIC_NOT_PHYSICAL` describes only that CI probe; it is not a required gate, physical observation or authorization.

A hosted run is only a packaging/test result. It is not approval to access LS5/PC4 or Bybit. No owner request may start a physical run until independent review and G0 are ready.

## Package and staging gate

The builder is restricted to exact GitHub-hosted Windows CI for `YehorBabenko88/bybit-cluster-grid`, job `s0-windows`; it rejects physical LS5/PC4 hosts. Its only supported invocation is `python -m tools.build_s0_package` in the reviewed checkout. Do not build a package locally. The expected future outputs are:

Hosted Windows observed `D:\` owned by NETWORK SERVICE (`S-1-5-20`), outside the custody trust set. That rejection is intentional. Native build/extraction/owned-resource fixtures use fresh GUID children of the actual .NET-resolved C: LocalAppData. Subsequent native evidence identified TrustedInstaller as the owner of `C:\`. Under the declared trusted-OS boundary, its exact canonical service SID is accepted only as **owner of the actual OS volume-root ancestor**, independently obtained from `GetSystemWindowsDirectoryW`, and rechecked on each guard. This does not trust any TI ACE, strict package/data root, file, descendant or other volume. Unknown/API-error/ambiguous observations and dangerous untrusted ACEs still block. Existing filesystem ACLs are never repaired by CI tooling.

- `s0-package/physical-smoke-s0-windows-py312-<HEAD>.zip`
- `s0-package/package-receipt.json`

The receipt pins the ZIP bytes and actual HEAD/tree/run/attempt. `s0-package.json` pins every other ZIP member by SHA256 and size; it cannot pin its own bytes or the enclosing ZIP. Both runtime `._pth` files contain only `stdlib.zip`, `DLLs`, `Site`, `App` and no `import site`. The S0 entry is `runtime/App/s0.py`.

An authorized human must stage the independently verified ZIP into an **already selected, protected trusted parent**. The selected protected `PackageRoot` must contain the original matching archive under the exact name `source.zip`; `PackageZip` must be `PackageRoot/source.zip`. This original archive is the sole explicit exclusion from the extracted manifest member closure; every other extracted member must match the manifest, with no unlisted additions. The wrapper does not download, expand, bootstrap or repair package custody. There is no atomic staging helper in this change. Do not unpack into a shared writable directory and attempt to fix its ACL afterward. Validate parent custody first, then follow a separately reviewed owner staging procedure; verify the full extracted member closure and resulting package root custody before launching its Python. A ZIP digest alone does not establish the custody of an extracted executable.

The following future gate deliberately stops until the operator fills values from G0. It does not stage or execute anything:

```powershell
$ProtectedBootstrapParent = $null # owner-selected existing protected trusted parent
$IndependentReviewComplete = $false # private review record
$G0Ready = $false # private owner record
if (-not $ProtectedBootstrapParent -or -not $IndependentReviewComplete -or -not $G0Ready) {
    throw 'BLOCKED: select and verify protected bootstrap parent, independent review and G0 first'
}
# STOP here for the separately reviewed human staging procedure.
# No Expand-Archive / ACL rewrite / automatic download is supplied.
```

## Inputs and closed plan

All values below are public pins or paths. Never pass a secret in arguments or environment. The launcher leaves the parent environment untouched and clears the child environment before copying only SystemRoot, WINDIR, USERPROFILE, LOCALAPPDATA, USERNAME and COMPUTERNAME. Child PATH is fixed to SystemRoot/System32; TEMP and TMP are exactly Root/temp. No Python overrides, database/Grid settings, proxies or API credentials are inherited. The wrapper never creates that temp path: preparation must create its protected fresh pair and role temp children; before then it may be absent, and code needing temporary storage must fail closed rather than fall back elsewhere. The runtime also rejects forbidden configuration if invoked directly.

`--config` for **LS5 Prepare** identifies `protectedInput/s0-plan.json`, a private approved plan file with exactly these fields:

| Field | Constraint |
|---|---|
| `schema`, `profile` | Integer `1`, string `PHYSICAL_SMOKE_S0` |
| `head` | Exact reviewed lowercase 40 hex HEAD |
| `run_id` | Fresh lowercase canonical UUID4 |
| `duration_seconds`, `symbol` | Integer `300`, string `BTCUSDT` |
| `bybit_url` | Exact `wss://stream.bybit.com/v5/public/linear` |
| `coordinator_ip`, `worker_ip` | Distinct approved literal IPv4 addresses, private or CGNAT ranges |
| `port` | Approved integer 49152–65535, excluding 55432 and 55433; not busy |
| `operator_sids` | Object with exactly `LS5` and `PC4`, full distinct approved user SIDs |
| `hostnames` | Object with exactly logical roles `LS5` and `PC4`, values the independently observed exact uppercase Windows GetComputerNameW NetBIOS machine names |

The following plan template is intentionally invalid until the owner supplies all G0 values. Null addresses/SIDs/hostnames and the placeholder head/run ID must never be treated as approval. Port 49441 is only a proposal, subject to G0 and the busy-port check.

```json
{
  "schema": 1,
  "profile": "PHYSICAL_SMOKE_S0",
  "head": "REPLACE_WITH_REVIEWED_40_HEX_HEAD",
  "run_id": "REPLACE_WITH_FRESH_LOWERCASE_UUID4",
  "duration_seconds": 300,
  "symbol": "BTCUSDT",
  "bybit_url": "wss://stream.bybit.com/v5/public/linear",
  "coordinator_ip": null,
  "worker_ip": null,
  "port": 49441,
  "operator_sids": {"LS5": null, "PC4": null},
  "hostnames": {"LS5": null, "PC4": null}
}
```

No extra fields, duplicate JSON keys, floats, NaN, unbounded/deep JSON, endpoint hostnames in place of literal IPs, wildcards or credential fields are accepted. `LS5` and `PC4` are logical roles, not assumed literal machine names: record the actual uppercase Windows NetBIOS names in `hostnames` without alias normalization. A machine called `LS-5` must never be silently treated as `LS5`; unknown names remain null and BLOCKED. Runtime matches the actual machine against the selected role's exact configured hostname and full operator SID. `Root` must be a fresh `GridS0-<UUID4>` path under the approved trusted parent. Plan UUID4 and root identity must follow the CLI's validated fresh-run contract.

## Future commands after the gate

These are manual commands for a future separately authorized run. No command below has been executed as part of this implementation. Fill the public pins from the owner record and future CI receipt on **each** machine; use that machine's local protected paths.

```powershell
$ExpectedHead = Read-Host 'Reviewed exact Git HEAD from G0'
$ExpectedPackageSha = Read-Host 'ZIP SHA256 from independently verified hosted receipt'
$PackageRoot = Read-Host 'Already staged and custody-verified absolute package root'
$PackageZip = Join-Path $PackageRoot 'source.zip' # original independently verified archive
$Root = Read-Host 'Approved absolute fresh GridS0-UUID4 root (LS5 prepare), or local role root'
$Config = Read-Host 'Absolute protected input s0-plan.json (LS5 Prepare), input PC4/config.json (PC4 Prepare), or local prepared role config.json'
$Wrapper = Join-Path $PackageRoot 'installer/physical-smoke-s0.ps1'
$PowerShell51 = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell/v1.0/powershell.exe'

# Pure plan: emits JSON, no subprocess or writes; default action is Plan.
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Plan

# Do not call Preflight on an absent/unprepared root. It requires a prepared role.
```

Each command below starts a fresh Windows PowerShell process. The native helper type must not already be loaded in that process; this prevents reuse of unverified assembly bytes across actions. Do not replace these calls with repeated in-process script invocation.

`Plan` never grants permission and its command remains null. Missing pins yield `BLOCKED`. Before Prepare, G0 uses separately approved manual read-only custody/token/network/source inspections; wrapper Preflight is not a bootstrap or an absent-root inspection tool. Once a local role is prepared, successful read-only Preflight is evidence about its current inputs, not authorization to run the next phase.

Future G0 reviewers may collect the following read-only facts in the approved physical session before preparation. Run them only in the approved actual target session; compare the full observed names without removing hyphens or normalizing aliases. They are inspection inputs, not an automated PASS or a substitute for the runtime token/custody rules. `$ProtectedInput` and `$ApprovedPort` must already come from the owner record; do not guess them.

```powershell
hostname
Get-CimInstance -ClassName Win32_ComputerSystem | Select-Object Name
whoami /user
whoami /groups
whoami /priv
Get-Acl -LiteralPath $ProtectedBootstrapParent | Format-List Owner,AreAccessRulesProtected,Access
Get-Acl -LiteralPath $PackageRoot | Format-List Owner,AreAccessRulesProtected,Access
Get-Acl -LiteralPath $ProtectedInput | Format-List Owner,AreAccessRulesProtected,Access
Get-FileHash -LiteralPath $PackageZip -Algorithm SHA256
Get-NetIPAddress -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv4
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq $ApprovedPort }
```

Do not interpret no listener output as permission to bind; the role preflight performs its own port check. Owner-reviewed Tailscale identity/routes and full SSH fingerprint must be supplied separately from the approved existing tools/session. This change provides no SSH staging command or Tailscale repair command.

On LS5 only, with fresh parent/root and plan approved:

```powershell
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Prepare -Approved
```

LS5 preparation creates the fresh pair root named exactly `GridS0-<run_id>` plus `temp`, `LS5/temp` and `PC4/temp`. Both role children contain `config.json`, `tls-key.pem`, `tls-cert.pem`, `ca.pem`, `peer-cert.pem` and `stop.json`. Only the local LS5 role receives `prepared.json`, which records its native root and stop-file identities. The PC4 child is transfer material, **NOT READY** for execution, and has no local prepared marker. Fresh protected objects use the three trusted Full Control ACEs above. The temporary CA private key exists only in memory; role keys remain private, unlogged and excluded from evidence. Preparation starts no transport or collection.

Stop for owner inspection and separate transfer approval. Transfer **only** these six PC4 files through the separately authorized encrypted verified SSH channel into the approved protected PC4 input directory: `ca.pem`, `tls-cert.pem`, `tls-key.pem`, `peer-cert.pem`, `config.json`, `stop.json`. Never transfer the LS5 private key, LS5 `prepared.json`, or any LS5 role content. The six-file transfer includes PC4's private key: do not upload it to GitHub, CI artifacts, chat or a shared folder. No transfer command is supplied until the exact channel, fingerprint and receiving custody have been approved. Do not improvise extraction or ACL repair.

On PC4, preparation is a separate approved local action. Set `$Root` to a **new** local PC4 pair root named `GridS0-<the same run_id>` under PC4's approved trusted parent; set `$Config` to the received protected input `PC4/config.json`; set PC4's local package paths. Then:

```powershell
# PC4 only, after independently verified encrypted transfer and new local-root approval.
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Prepare -Approved
```

PC4 Prepare validates the received role configuration/certificate hashes and copies checked role bytes into its fresh local `PC4` child, creates private pair/role temp children, and creates its own `prepared.json` with local native root/stop identities. A copied prepared marker is never a substitute for this step. There is no Stage action.

For each role, set `$Root` to its prepared local role directory and `$Config` to that directory's `config.json`, then run the prepared-role preflight:

```powershell
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Preflight
```

Start the Coordinator on LS5 first. Execute stays foreground and prints its final result on exit; it does not print a live readiness notification. Use the separate read-only LS5 check below, then start the PC4 Worker within **30 seconds of listening** (the registration deadline), without extending either process's budget:

```powershell
# Foreground console on the corresponding physical role; explicit approval required.
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Execute -Approved
```

In a second LS5 operator console with the same already approved local variables, inspect only the newly prepared role. A missing file/listener or uncertain identity is STOP, not permission to adopt another process:

```powershell
$ErrorActionPreference = 'Stop'
$RoleConfig = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$Claim = Get-Content -LiteralPath (Join-Path $Root 'claim.json') -Raw | ConvertFrom-Json
if ($Claim.head -cne $ExpectedHead -or $Claim.run_id -cne $RoleConfig.plan.run_id -or $Claim.role -cne 'LS5') { throw 'S0_CLAIM_CONTEXT_BLOCKED' }
$Owned = Get-Process -Id ([int]$Claim.pid) -ErrorAction Stop # read only; never Kill/Stop-Process
if ($Owned.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [long]$Claim.creation_filetime) { throw 'S0_PROCESS_IDENTITY_BLOCKED' }
$Listener = @(Get-NetTCPConnection -State Listen -LocalAddress $RoleConfig.plan.coordinator_ip -LocalPort $RoleConfig.plan.port -ErrorAction Stop | Where-Object OwningProcess -eq $Owned.Id)
if ($Listener.Count -ne 1) { throw 'S0_OWN_LISTENER_NOT_READY' }
'S0_OWN_LISTENER_OBSERVED_NOT_AUTHORIZATION'
```

This is a momentary observation, not continuous custody or a physical PASS. The native launcher's owned process handles and Job enforce lifetime; the check never signals a PID.

Do not restart, reconnect manually, extend the run, reuse a root, or change parameters to turn a partial run into a pass. Use new review/authorization and fresh preparation for any later attempt.

Separate operator consoles can request status or stop for their own prepared role:

```powershell
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Status
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Stop -Approved
& $PowerShell51 -NoProfile -File $Wrapper -Root $Root -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Evidence -Approved
```

The wrapper receives the native launcher's owned PID, creation file time, exit code, budget, timeout and scope receipt. Execute is limited to 300 seconds and other actions to 60 seconds. On timeout it reports `S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED`; closing only its owned Job terminates the owned child. A parent crash also closes that Job. There is no PID lookup/kill, arbitrary executable launch or foreign-process signaling. An abrupt timeout may leave incomplete evidence and cannot produce acceptance. The console is foreground and output is not redirected to a log. This lifetime limit is separate from network policy and grants no G1 authority.

`TimedOut` dominates the observed OS exit code. Hosted owned-Job-close observations returned `exit_code=0` with `timed_out=true`; keep that actual value in evidence, and still reject the S0 action. The receipt validator may accept this as an **expected timeout fault-test observation**, never as a successful S0 execution. Five pure PowerShell 5.1/7 regressions bind this behavior to the actual wrapper's throw-only completion branches. Token probe handling also retains exact scalar/variable-size contracts; Win32 24 is accepted only for a four-byte TokenElevation probe, with 14 mandatory native policy cases.

`Stop` writes only the role's own stop notification, which its process polls. The exclusive claim uses the actual process PID and creation time for evidence/identity association; it is never a license to kill a PID. It sends no foreign signal and never kills a PID. Stop each role using its own local custody and pins. There is no `Cleanup` action; retain evidence and private files in protected custody until the owner separately decides retention/disposal.

## Phase results and evidence

| Phase | PASS evidence | FAIL / BLOCKED |
|---|---|---|
| Hosted package | Exact source and ZIP receipts, bounded member manifest, test report | Dirty/mismatched source, host guard, dependency closure, license or manifest failure |
| Human staging | Independent ZIP/source comparison, trusted-parent and extracted closure/custody record | No selected trusted parent, unknown bootstrap provenance or unverified executable |
| Plan | Closed inputs displayed without action authority | Missing pins or malformed plan; no command |
| Preflight | Prepared local role, actual machine/SID/token, custody, source/package, endpoint configuration and LS5 port checks; manual G0 independently supplies route/interface/Tailscale evidence | Any mismatch or unavailable evidence; no repair |
| Prepare | LS5 paired material/local marker, then separately approved PC4 fresh local import/marker; protected roots and public certificate fingerprints | Existing root, wrong host/token, unsafe paths or partial preparation; do not reuse |
| Execute | Foreground role events, authenticated registration/heartbeat/assignment, public message counters and bounded monotonic interval | Policy/protocol/network failure or early stop; stop and preserve partial evidence |
| Status / Stop | Role-local verified status / own stop notification evidence | Unknown role/root, corrupt status or invalid custody |
| Evidence | Both role manifests, hashes, timeline and counters agree; actual healthy collection ≥240 seconds | Missing role, corrupt/mismatched evidence or insufficient collection: `PARTIAL` / blocked assessment |

Evidence is a new role-root `s0-evidence.zip`; it is bounded and excludes private keys, CA private material, credentials and configuration. Retain both roles' archives for joint assessment. Evidence explicitly carries `g1_execute=false`, physical SID/ACL `0/10 NOT_RUN`, and deployment NO-GO; an S0 observation cannot change those results. Retain the role evidence files, hashes, expected source/package pins, run identity, public certificate fingerprints, preflight summaries, outcome and actual healthy collection interval. Never label tests using synthetic fixtures as actual physical observations.

## Mandatory stop conditions

Stop and preserve evidence on invalid source/package pins, changed ACL/custody or token, route/interface/Tailscale mismatch, wrong peer/role, port busy, timestamp failure, replay/dedup conflict, message/byte/time quota violation, disconnect beyond the allowed budget, missing role evidence, evidence corruption or any unexpected external endpoint or authenticated/trading operation. Treat unavailable verification as BLOCKED. Do not open firewall ports, repair network settings, change ACLs, elevate, kill unrelated processes or modify production to make S0 pass.

A completed S0 report may state only its observed public-data behavior and limits. It cannot claim G1 readiness, full Grid behavior, persistent reliability, HA or production safety.

## Enforced private namespaces and remaining staging gate

The wrapper obtains LocalApplicationData from the Windows known-folder API. The
package must be its direct child `GridS0Package-<UUID4>` with the original ZIP
inside named `source.zip`. Preparation input must be in another direct child
`GridS0Input-<UUID4>` (`s0-plan.json`, or `PC4/config.json` and its role files).
The new pair root must be a direct child `GridS0-<run UUID4>`; execution uses
its logical `LS5` or `PC4` child. These names do not authorize creating them.
ProgramData, Program Files, GridLab, PostgreSQL and existing Grid trees cannot
be chosen as these roots. Preparation/preflight require 512 MiB free on the
private-profile volume; execution stops below a 128 MiB free reserve and bounds
its journals. No space is reserved against concurrent unrelated applications.

Safe protected initial package/input staging is an external bootstrap
precondition, not an implemented `Stage` action. If there is no independently
approved method that creates fresh protected roots and verifies the exact ZIP
without adopting existing resources, staging has **BLOCKED/null command**.
Do not invent an `Expand-Archive -Force`, ACL reset, execution-policy bypass,
or direct-Python workaround. Owner must select this bootstrap before physical
S0 can be authorized. The package and all subsequent commands are reviewable
preparation; they do not themselves supply the missing staging trust anchor.
