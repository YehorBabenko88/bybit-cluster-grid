# Physical Windows infrastructure readiness — planning only

Baseline: Draft PR #216, SHA `b0d31eaaa2221da357ef6127fca3f0207c4248e2`. This independent branch does not modify PR #216, pinned physical packages, services or production systems.

## Safety and scope
- **NO-GO** until coordinator explicitly authorizes physical observations and subsequent tests.
- PC4 physical SID/ACL cases **0/10 NOT_RUN**; VM principal cases **0/12 NOT_RUN**.
- `readiness_passed=false` and `execution_authorized=false` are immutable outputs of this offline analyzer, including when all user-supplied controls say PASS.
- Do not run LSA queries, SSH, Tailscale commands, Windows services, token probes, actor launches or ACL changes from this branch.
- Never publish real SID, SDDL, tokens, credentials or raw private inventory in CI logs or issue comments.

## Read-only inventory contract (future owner-approved observations)
Each of the 15 controls in `infra_readiness.contracts.CONTROLS` must have `status` in PASS/BLOCKED/UNKNOWN. A claimed PASS additionally requires two distinct, nonempty evidence and witness references; these **do not authenticate** evidence. Unknown or missing control data never produces physical readiness.

LS5: verify machine identity, OpenSSH server/client configuration, SSH public-key and administrator scope, Tailscale device identity and grants/ACL, Windows Firewall, subnet routes and bypass paths. A successful SSH connection is not proof of Windows token or ACL isolation.

PC4: verify complete local account SIDs, enabled/lockout state, direct and transitive groups, relevant LSA logon rights and denies, owner/DACL/inheritance/reparse points of protected role parents, and effective access. `Get-LocalLogonRights.ps1 -CollectLocal` remains a separate opt-in diagnostic, **not** an effective-token evaluator.

Windows process creation: the existing PowerShell 5.1 credentialed `ProcessStartInfo` path uses `CreateProcessWithLogonW` interactive logon semantics, not batch/service. `SeBatchLogonRight` alone is insufficient; evaluate effective `SeInteractiveLogonRight` and `SeDenyInteractiveLogonRight` for all applicable groups. Deny wins for matching logon type. Do not infer rights from `TokenPrivileges`. The `seclogon` state must be independently confirmed; under a no-service-state-change policy, Stopped/Disabled/UNKNOWN means BLOCKED. A demand-start service transition is still a state change.

## Staged verification and stop gates
1. **Planning and authorization:** approve host inventory, precise permitted commands, observer independence, private evidence custody, rollback/STOP ownership and maintenance window.
2. **LS5 inventory:** authorized local read-only host/SSH/Tailscale/firewall observations. Verify no unreviewed alternate admin route. UNKNOWN -> BLOCKED.
3. **PC4 accounts and logon:** verify identity, effective group allow/deny, `seclogon`, caller constraints (elevated human operator, not LocalSystem), executable/package/desktop access. No automatic repair.
4. **PC4 filesystem:** verify owner, DACL, inheritance, link traversal, role separation and protected parents without writing fixtures.
5. **Package custody:** verify pinned source and artifact SHA independently; do not substitute newly built CI artifacts for the physical pin.
6. **Physical tests, separately authorized only:** launch role actors with live token witnesses and negative ACL access cases. On unknown PID/start outcome, never retry, clean fixtures or claim PASS. Keep controller and actor timeout semantics distinct; a timed-out `Process.Start` may have created a process.
7. **Independent evidence review:** confirm all cases, private logs, process termination certainty, token group attributes, logon session and integrity. Do not generalize interactive-token findings to Windows service/batch tokens or PGDATA.

## Machine-readable offline example
```python
from infra_readiness.contracts import CONTROLS
import json
report = {
    "schema_version": 1,
    "readiness_passed": False,
    "execution_authorized": False,
    "physical_cases": ["NOT_RUN"] * 10,
    "controls": {name: {"status": "UNKNOWN"} for name in CONTROLS},
}
with open("offline-infra-inventory.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
```
Then run `python -m infra_readiness.cli offline-infra-inventory.json` on an offline developer environment. Exit 2 is expected for blocked/unknown evidence. No network or Windows API access is performed. A PASS is an unverified claim unless independently authenticated outside this model.

## Remaining blockers
Effective interactive allow/deny, `seclogon` state, PC4 account restrictions, full token groups/attributes and logon-session proof, LS5/PC4 SSH/Tailscale trust boundary, effective NTFS access and observer independence are not verified by CI. These require distinct, explicit authorization before physical work. Never merge or deploy solely on green offline CI.
