# UserProfile V1 S0 — operator runbook, NOT_AUTHORIZED

LS5 Coordinator and PC4 Worker here mean the public-only `s0_smoke` adapter,
not the PostgreSQL/production `grid` runtime. BTCUSDT only, public Bybit V5 linear
WebSocket, no keys/orders/trading, 300-second outer process limit. This is not
production Grid acceptance, an air-gap, or protection from the operator/admin.

**Until exact-head CI, original artifact verification, independent acceptance
and explicit per-action owner approval: physical S0 NO-GO.** All20 G1 phases
remain BLOCKED/null argv. Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO.
No instruction below has been executed on a physical host by this change.

## Gates and implementation

The legacy LocalAppData entry points keep their scope and policy. New entry
points have `AtUserProfileV1` in their names; there is no fallback. The runtime
PowerShell/CLI selects `-ParentScope UserProfileV1` / `--parent-scope UserProfileV1`.
Never combine roots/scopes between either mode.

`SHGetKnownFolderPath(FOLDERID_Profile,0x4000,NULL)` is crosschecked with
`GetUserProfileDirectoryW` on the same query-only current primary token. Medium,
SID, groups/privileges, no impersonating thread, AppContainer or package identity
are checked. NTFS/OS-volume ancestors are pinned with identities/security stamps;
unknown effective replacement/control ACE, reparse, ACL drift or API error blocks.
Creation uses a protected descriptor with native relative FILE_CREATE; publication
is no-replace. Source files, including Python/DLLs, remain read/share-pinned through
child exit. Every runtime action reacquires the same parent policy. Prepared role
receipts bind scope, parent FileId and ACL digest across stop/restart inspection.

No existing ACL, user, service, task, firewall, SSH, Tailscale, PostgreSQL or release
is changed. Partial transactions are retained; they are never adopted or removed
automatically. Same-user malicious code, administrators and a compromised OS are
outside this trust boundary. Non-BMP profile names are conservatively blocked by
the native V1 resolver. No capability SID is granted new trust.

| Gate | PASS | FAIL/BLOCKED |
|---|---|---|
| CI/package | exact SHA, all required cells, original ZIP/manifest/Git pins agree | queued/skipped/red, substituted run/attempt, missing receipt |
| Independent acceptance | separately authored review of original evidence/package | pending/unavailable; a producer report is insufficient |
| Local token | real local Medium token and exact host/account | elevated/SSH-admin/unknown; do not modify accounts |
| Parent/source | native V1 lease, full ancestry, exact ZIP and source custody | alias/reparse/mount/unknown write/control/drift/API failure |
| Transfer | separately approved PUBLIC_NO_KEYS rehearsal with pinned SSH key and stable receiver | unknown SFTP behavior/writer/custody/deadline |
| Physical execution | separate exact head/run/hosts/resources/expiry/argv owner grant | any binding absent; approval does not follow from test PASS |

CI's shell/control matrix is PS5.1/7 × Python3.11/3.12. The portable **embedded
runtime remains Python3.12**, reported in its manifest. Do not call this an
embedded-Python3.11 physical package. Native profile fixtures use real restricted
Medium processes and GUID resources on hosted Windows only; no physical PASS.

## 1. Read-only console identity and authenticated initial load

On **each real host**, use its existing local non-elevated console. Expected LS5
is `LS5\LS-5` /100.103.160.110; expected PC4 operator is `PC4\ls4`, not the elevated
SSH token. If hostname/account differs, STOP. These simple outputs do not prove
Medium integrity; the native observer below must also succeed.

```powershell
hostname
whoami
$ExpectedSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$ParentScope = 'UserProfileV1'
$S0Shell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell/v1.0/powershell.exe'
$ExpectedHead = Read-Host 'Exact independently accepted CI HEAD'
$ExpectedSha256 = Read-Host 'Original inner ZIP SHA256 from independent evidence'
$SourceZip = Read-Host 'Absolute path of inert original portable ZIP'
$TargetRoot = Read-Host 'Exact proposed fresh GridS0Package-UUID path from owner manifest'
$Action = 'ObserveToken'; $Approved = $false; $DiagnosticStages = $false
```

Execute only the independently reviewed **literal starting at `Set-StrictMode`**
in `PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md`, with the variables above. Do not copy
its legacy `ParentScope` assignment. Never run an extracted loader to establish
its own trust. The literal captures/authenticates ZIP bytes before loading the
helper, then calls the explicit native V1 Plan/observer. This is trusted-code
read-only execution, not a pure/hermetic operation. No bypass of execution policy.
Use a fresh console on a repeated load; the loader rejects an already loaded type.

After successful authenticated load, this is read-only and grants no authority:

```powershell
$ParentProof = [GridS0.Bootstrap]::HoldUserProfileV1($ExpectedSid)
try { $Profile = $ParentProof.ParentPath; $ParentId = $ParentProof.ParentIdentity; $ParentProof.Check() }
finally { $ParentProof.Dispose() }
$RunId = Read-Host 'Owner-pinned fresh run UUID (same on both hosts)'
$PairRoot = Join-Path $Profile ('GridS0-'+$RunId)
$RoleRoot = Join-Path $PairRoot 'LS5' # PC4 console: use 'PC4'
```

No `USERPROFILE`/`LOCALAPPDATA` environment substitution determines these roots.
Publish private token/custody receipts only through the approved evidence process.

## 2. Staging — separate permission, each host

Approve exact source ZIP/head, SID/session, target and expiry first. No directory
exists yet merely because Plan passed. A partial or existing target means STOP.

```powershell
$OwnerStageApproved = $false # owner authorization is absent by default
if (-not $OwnerStageApproved) { throw 'S0_STAGE_NOT_AUTHORIZED' }
$Staged = [GridS0.Bootstrap]::StagePackageAtUserProfileV1($bytes,$ExpectedSha256,$ExpectedHead,$TargetRoot,$ExpectedSid,$true)
$PackageRoot = $TargetRoot
$PackageZip = Join-Path $PackageRoot 'source.zip'
$ExpectedPackageSha = $ExpectedSha256
$Launcher = Join-Path $PackageRoot 'installer/physical-smoke-s0.ps1'
```

`$bytes` is the original authenticated captured byte array from the literal;
Stage copies and revalidates it. Re-observe identity/custody if the console/session
or source changed. Do not create parents, repair ACLs or use another path on failure.

## 3. LS5 plan input and Prepare — separate permissions

Build canonical UTF-8 JSON using the existing plan schema in `PHYSICAL_SMOKE_S0.md`:
exact accepted HEAD/run, duration300, BTCUSDT, literal
`wss://stream.bybit.com/v5/public/linear`, verified LS5/PC4 IPs/hostnames/operator
SIDs and an independently checked unused high port. No `.env` or database fields.
The native validator rejects noncanonical JSON and incompatible values.

```powershell
$InputRoot = Read-Host 'Owner-pinned fresh GridS0Input-UUID path directly under native Profile'
# $PlanBytes and $PlanSha: approved canonical bytes and their SHA256, kept in memory.
[GridS0.Bootstrap]::PlanInputAtUserProfileV1($PlanBytes,$PlanSha,$ExpectedHead,$RunId,$InputRoot,$ExpectedSid)
$OwnerInputApproved = $false
if (-not $OwnerInputApproved) { throw 'S0_INPUT_NOT_AUTHORIZED' }
[GridS0.Bootstrap]::StagePlanInputAtUserProfileV1($PlanBytes,$PlanSha,$ExpectedHead,$RunId,$InputRoot,$ExpectedSid,$true)
$OwnerPrepareApproved = $false
if (-not $OwnerPrepareApproved) { throw 'S0_PREPARE_NOT_AUTHORIZED' }
& $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Prepare -ParentScope UserProfileV1 -Root $PairRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $InputRoot 's0-plan.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Approved
```

Prepare creates only the fresh protected pair/role/temp directories and ephemeral
TLS material for this run. Existing pair/role directories are not resumed/adopted.

## 4. Transfer — public rehearsal before private role material

Use the exact pinned host key and reviewed Windows OpenSSH binaries; never trust
an unauthenticated `ssh-keyscan` as authority. Native APIs do not open SSH/network
connections. They materialize/check only their owned export/recipient resources.

On LS5, after the respective explicit action approvals:

```powershell
[GridS0.Bootstrap]::PlanTransferProbeAtUserProfileV1($ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExportRoot,$ExpectedSid)
# Public NO_KEYS only, when specifically authorized:
# $Export = [GridS0.Bootstrap]::StageTransferProbeAtUserProfileV1($ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExportRoot,$ExpectedSid,$true)
# Later, a separately approved private export, never printed/uploaded:
# $Export = [GridS0.Bootstrap]::StageTransferExportAtUserProfileV1((Join-Path $PairRoot 'PC4'),$ExpectedHead,$RunId,$ExpectedPackageSha,$ExportRoot,$ExpectedSid,$true)
# $Known = [GridS0.Bootstrap]::StageTransferKnownHostsAtUserProfileV1($ExportRoot,$Export.Materialization.RootIdentity,$Export.PayloadSha256,$ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExpectedSid,$true)
# $Sender = [GridS0.Bootstrap]::OpenTransferSenderAtUserProfileV1($ExportRoot,$Export.Materialization.RootIdentity,$Export.PayloadSha256,$Known.KnownHostsSha256,$ExpectedSid)
```

On PC4's local standard console (after its own scope approval):

```powershell
[GridS0.Bootstrap]::PlanTransferSlotAtUserProfileV1($ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ReceiveRoot,$ExpectedSid)
# $Slot = [GridS0.Bootstrap]::StageTransferSlotAtUserProfileV1($ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ReceiveRoot,$ExpectedSid,$true)
# $Receiver = [GridS0.Bootstrap]::OpenTransferSlotAtUserProfileV1($ReceiveRoot,$Slot.Materialization.RootIdentity,$Slot.IncomingIdentity,$ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ExpectedSid,$true)
# Following actual pinned transfer and verified writer shutdown:
# $Receiver.Verify()
# [GridS0.Bootstrap]::PlanTransferImportAtUserProfileV1($Receiver,$ExpectedHead,$RunId,$ExpectedPackageSha,$Pc4InputRoot,$ExpectedSid)
# [GridS0.Bootstrap]::StageTransferImportAtUserProfileV1($Receiver,$ExpectedHead,$RunId,$ExpectedPackageSha,$Pc4InputRoot,$ExpectedSid,$true)
# & $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Prepare -ParentScope UserProfileV1 -Root $PairRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $Pc4InputRoot 'PC4/config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Approved
```

Use `build_transfer_plan_at_user_profile_v1()` for an inert exact-argv proposal,
with both parent identities, own roots and host/binary pins. It ALWAYS returns
BLOCKED/null argv and never starts a process. Real scp/SFTP interoperability,
recipient custody, writer shutdown and total SSH process bounds still need the
separately approved public rehearsal. Its receiver300s lease does **not** enforce
a total SSH process deadline. Do not close a safety handle to make scp succeed.
No private transfer until the rehearsal and owned-process stop proof are accepted.

## 5. Both hosts: Preflight, Execute, Status, Stop, Evidence

After import/Prepare, `$RoleRoot` and its own config differ only by local role.
Every dispatcher action below starts a fresh stock non-elevated PowerShell.
Do not invoke the launcher in the bootstrap console itself: its already-loaded
native type is deliberately rejected. No RunAs/credential/profile bypass is used.
Run the read-only application preflight first; it grants no Execute permission.

```powershell
& $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Preflight -ParentScope UserProfileV1 -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $RoleRoot 'config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha
```

Only after a separate300s LS5/PC4 Execute grant, start LS5 first, then PC4 in their
local standard consoles. These are proposals, not commands authorized today:

```powershell
# & $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Execute -ParentScope UserProfileV1 -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $RoleRoot 'config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Approved
# & $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Status -ParentScope UserProfileV1 -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $RoleRoot 'config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha
# Separately approved cooperative stop: writes only the identity-bound own stop slot, no PID signals.
# & $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Stop -ParentScope UserProfileV1 -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $RoleRoot 'config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Approved
# Following owned-process exit and evidence-export permission:
# & $S0Shell -NoLogo -NoProfile -NonInteractive -File $Launcher -Action Evidence -ParentScope UserProfileV1 -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $RoleRoot 'config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Approved
```

STOP on hostname/token/SID/head/digest/FileId/ACL drift, collision, unknown API
state, occupied port, unsupported SFTP behavior, stale lease, missing peer,
unexpected process, production/private endpoint, malformed/empty/stale feed or
deadline failure. No firewall/service/network/account/ACL fix is authorized.
Only the new process's unnamed Job can stop its child at the deadline. Preserve
logs/partial resources; no cleanup, PID guessing, taskkill, service stop or DB use.

Acceptance needs paired counters and hashes, exact original package/head, own PIDs
and creation times, bounded exit, fresh BTCUSDT orderbook/trades, no secret-bearing
files in evidence, and independent review. Hosted tests/technical AI review do
not supply physical authorization or Physical SID/ACL PASS.
