# LS5 + PC4 G0 readiness report

G0 verdict: **BLOCKED**. LS5 and PC4 have not been observed in this task. The supplied
IP addresses, userLS4, port8765, PG18 status, resources, accounts and directories are
UNVERIFIED historical/user inputs. No SSH/Tailscale/session/credential/host-key
connection was attempted. Preparation is not G1/G2 authorization.

## Reuse and separation

Existing collect-commissioning-inventory.ps1 is informational and suppresses some
provider errors; it also exports a raw computer name. It cannot be a fail-closed,
privacy-preserving readiness gate. collect-physical-node.ps1 deliberately blocks LS5,
requires runtime stopped and PG16. Those protections remain unchanged. Runtime Guard
is retained for production release switching; G0 must observe an existing coordinator
without stopping it, acquiring its release mutex or treating its directories as owned.

New installer/collect-physical-g0.ps1 is a separate metadata-only LOCAL observer.
Default PLAN_ONLY and ReadOnly without -G0Approved perform zero providers. Approval
switch is only an operator assertion, not verified access/identity or G1 authority.
When invoked by the owner it emits JSON to stdout; it does not write files, execute
version probes, connect to databases/health/remote nodes, modify accounts/ACLs/services/
tasks/firewall, acquire a mutex or stop processes. It never reads .env contents or
serializes command lines. Environment names are allowlisted, owner/account identifiers
are run-bound digests; C:\Users account components are redacted. Host ID is a digest of
MachineGuid and run ID, not the real computer name. Raw errors are discarded.

Metadata does NOT prove effective Windows tokens, DACL custody, machine-label binding,
file handles, reparse-free descendants, binary integrity or an independent observer.
Run only from an independently trusted checkout and Windows/PowerShell module chain,
under approved G0 access; a compromised OS/admin is outside this observer's guarantees.
An unknown provider/identity gives BLOCKED; reparse observation gives FAIL. No network
probe occurs implicitly. No administrative token is evidence of nonadmin isolation.

## Exact local owner G0 commands (NOT executed by Codex)

First verify Windows-supplied PowerShell, approved Git/Python paths and executable
ancestor custody independently; do not use ProgramData/runtime or broad-writable
GridLab Runtime/PostgreSQL/Fixtures as trusted toolchain. Do not run as SYSTEM.
At a local console on each already-authorized host, use fresh owner-approved values:

```powershell
$CandidateHead = '<reviewed exact 40-lowercase-hex commit>'
$RunId = [guid]::NewGuid().ToString('N')
$Node = 'LS5' # separately PC4, use the SAME run ID on both
$Checkout = '<already present protected checkout>'
$TrustedPython = '<independently verified Python3.11 or3.12 full path>'
$TrustedGit = '<independently verified Git full path>'
& $TrustedGit --no-optional-locks -c core.fsmonitor=false -C $Checkout rev-parse HEAD
# STOP on wrong HEAD or any custody/byte-manifest mismatch; HEAD alone is not trust.
# Do not run status/diff against untrusted .git config: clean filters may execute code.
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File "$Checkout\installer\collect-physical-g0.ps1"
# PLAN_ONLY; no host providers
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File "$Checkout\installer\collect-physical-g0.ps1" -Mode ReadOnly -G0Approved -NodeId $Node -Head $CandidateHead -RunId $RunId -SourcePath $Checkout
```

Do not paste output into public GitHub before owner privacy review. Capture stdout to
new evidence in a preexisting owner-controlled location; no overwrite. File capture
is an operator evidence action, not an ownership proof. Exit0 from collection means
report emitted, not READY. No files are collected in this task from either host.

Offline assessment on an approved review workstation:

```powershell
& $TrustedPython -m integration.physical_program --head $CandidateHead --run-id $RunId
& $TrustedPython -m integration.physical_program --head $CandidateHead --run-id $RunId --snapshots LS5-g0.json PC4-g0.json
# assess exit1 = BLOCKED/NO-GO; no execution path exists
```

Snapshots older than900s, future-dated, mismatched HEAD/run, duplicate host digests,
missing checks/unknown types, unsafe data fields and authority promotion are rejected.
Port conflicts and an existing planned root are NO-GO. A self-consistent complete
report still needs independent G0 review; it cannot turn HOST_VERIFIED or G1 on.
Formal observation/profile schemas plus cross-field Python validation are mandatory.
Local clock freshness is replay hygiene, not trusted time or durable anti-rollback.

## Observation coverage and unresolved facts

| Requested observation | LS5 | PC4 | Mechanism / limitation |
|---|---|---|---|
| OS build/architecture, CPU/RAM/disks | BLOCKED | BLOCKED | CIM metadata only |
| Python/.NET/PS installations/versions | BLOCKED | BLOCKED | resolved PE file metadata, not executed/custody proof; parallel installs not exhaustive |
| PG18 service/version | BLOCKED | BLOCKED | service metadata; pg_ctl-launched instance may have NO service, process/listener and SQL review still needed |
| Existing DBs/roles/connections | BLOCKED | BLOCKED | optional separately approved read-only SQL below |
| Listeners/port conflicts | BLOCKED | BLOCKED | point-in-time Get-NetTCPConnection; no bind reservation |
| Coordinator/Worker/process identity | BLOCKED | BLOCKED | PID/creation/path + private command classification; PID reuse/handles unproven |
| Services/Grid tasks | BLOCKED | BLOCKED | informational, never owned or changed; no task action arguments exported |
| Tailscale/SSH/reachability | BLOCKED | BLOCKED | service state only; no routing/login or historic IP assumption |
| Firewall/network isolation | BLOCKED | BLOCKED | inventory availability only, effective ACL/egress unproven |
| Grid directories/ancestors/ACL | BLOCKED | BLOCKED | metadata/reparse observation; no effective-access/native custody proof |
| Local account SID/readiness | BLOCKED | BLOCKED | fixed test accounts, digested SID, direct admin positive only; unknown is null, no enabling |
| Environment/secret custody | BLOCKED | BLOCKED | names only, no values or .env reads; protected config unresolved |
| Source/release manifest | BLOCKED | BLOCKED | file SHA256 only; trusted manifest/whole closure must be independently verified |
| Health/API version/fencing | BLOCKED | BLOCKED | not probed: trusted endpoint + observer approval required |
| Parallel foreground feasibility | BLOCKED | BLOCKED | current runtime unknown; no Windows physical executor or kernel isolation acceptance |

## Optional G0 PostgreSQL metadata (owner only)

No SQL ran in this task. Only after owner verifies current destination/role/binary and
read-only access, planning/physical-first-boot/g0_metadata.sql may run with explicit
loopback host and the OBSERVED port (not a historical default). It uses BEGIN READ ONLY,
5s statement/1s lock timeout, catalogs only, no table contents/passwords/role names,
and ROLLBACK. OIDs/flags avoid personal names. It neither prepares nor repairs schema.

```powershell
& $VerifiedPsql -X --no-password --set=ON_ERROR_STOP=1 --host=127.0.0.1 --port=$ObservedApprovedPort --username=$ApprovedMetadataRole --dbname=postgres --file="$Checkout\planning\physical-first-boot\g0_metadata.sql"
```

Use an independently protected passfile/existing approved authentication; no secrets
in argv, logs, GitHub or newly written .env. Connection failure or wrong observed
endpoint =>STOP, no fallback port/user/DSN. A metadata connection is only G0 if explicitly
within owner's existing read-only authorization; otherwise retain BLOCKED/manual plan.

Health/SSH checks must likewise use freshly confirmed addresses/aliases and pinned
host keys; do not use saved100.x addresses or LS4 to bypass access. No acceptance
script here initiates these connections. Owner must approve exact endpoint and GET
semantics and independently redact the response before export.

## P0/P1/P2 and approvals

P0 physical run remains unauthorized and unproven; historical LS5 writable executable
ancestors/config exposure require independent current custody findings, not an assumed fix.
P1: no approved per-run Windows executor/handle ownership/OS egress containment; disabled
accounts/token readiness, disposable PG18 bootstrap and source trust unresolved. Existing
runtime authorization reproductions still block deployment. P2: partial metadata inventory,
point-in-time TOCTOU, local clock, hashes without independent provenance.

Owner decisions needed: authorize exact G0 access/host identities and metadata endpoints;
review signed evidence and current service coexistence; select independently protected
source/runtime/data/config custody and nonadmin identities; approve exact G1 resource
scope, network isolation, secrets, PG cluster/roles, processes, faults, time limit,
STOP authority and separate cleanup. No blanket approval or G0 PASS enables G1/G2.
G2 services/tasks/ACL Apply/production DB/deployment remain independently forbidden.
Physical SID/ACL PC4:0/10 NOT_RUN. Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO.

Additional boundaries: direct UNC/device/ADS/dot-alias source paths are rejected;
source ancestors are checked for reparse before hashing. PATH entries are screened
before tool lookup. This does not prove mapped-drive/ancestor TOCTOU or hostile
provider isolation; those remain native-custody prerequisites, not metadata guarantees.
Eight mocked-provider/AST cases per PS5.1/7 passed; no real host collection occurred.

Hosted-only follow-up identified native metadata-handle sharing limitations; the
proposed share-bearing read-access/protocol fix must pass GUID fixtures before any
physical custody claim. Hosted297fcb7 passed56 managed cases and the held-leaf rename check
returned sharing violation32; the subsequent session recheck failed framing.
The strict UTF8 stream-reader correction and57-case inventory are pending hosted CI. These changes do not authorize G0 native collection.
