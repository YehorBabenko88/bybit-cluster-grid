# L1 witness channel decision — offline proposal

Status: **L1 NO-GO — human choice and independent review outstanding.**
Physical deployment / L2: **NO-GO**. Schema-2 and every authorizing flag remain
false. Twelve guest scenarios remain NOT_RUN. This document describes proposed
flows, not instructions to configure a host, gateway, device or service.

Frozen planning base: PR #212, `2552cf8568a21d4a57a2aacc57ccdbc9861ea5c4`.
Frozen offline RC: PR #211, `83c7c034668d02ce833e4f9750409b74641b9070`.
Neither predecessor is changed. Their offline successes establish no physical
trust, durable storage, independent ownership, or authority to execute.

## Decision and alternatives

Neither alternative is selected or recommended for automatic adoption. A is
suitable only for an explicitly asynchronous experiment. B is a candidate when
bounded live freshness is required, contingent on a separately reviewed channel
and independent endpoints. Choosing B does not relax the original private-only
network contract: it requires a new, reviewed network architecture, not a hidden
extra NIC or route in that contract. These alternatives cannot be silently mixed.

| Property | A: physical isolation and supervised shuttle | B: dedicated lab-only witness channel |
|---|---|---|
| Network boundary | No routable link across lab boundary; removable evidence media is an attack surface | Deny by default gateway; only reviewed witness protocol destinations, no production, internet transit, NAT bypass or general routing |
| Proposed flow | Lab challenge/export → two-person quarantine/content validation → independent witness A/B → returned signed receipts → offline verification | Lab challenge → untrusted constrained gateway → separately administered A/B → end-to-end signed receipts |
| Trusted time | Signed receipt establishes what time an external authority asserted; import delay is unbounded | Independent time origin plus bounded transport delay/uncertainty must be measured; gateway clock is never authoritative |
| Freshness | Cannot prove two-second/live freshness; replay checks and nonce binding do not remove delay | UNVERIFIED until trustworthy time, deadline enforcement, independent receipt verification and delay/fault tests exist |
| Replay / rollback | Anchor CAS and single-use challenge still required outside snapshot domain | Same requirement; TLS or an online gateway alone provides no monotonic durable history |
| Independence | Two custodians, separate witness admins/storage/key custody; shared media reader can correlate compromise | Two endpoints/admin/storage domains; one gateway is a common censor/replay surface, never a third observer |
| Availability | Manual latency, lost/damaged media; fail closed on missing receipt | Gateway outage/partition blocks progress; fail closed rather than reduce 2-of-2 to 1-of-2 |
| Recovery | Preserve disputed media and external ledger; issue fresh challenge only after reconciliation | Preserve gateway/endpoint evidence; reconcile both durable ledgers before issuing fresh epoch |
| Additional equipment | Dedicated quarantine reader, controlled media, independent witness devices/storage, evidence archive | Dedicated restricted gateway and isolated channel, independent witness devices/storage, protected evidence archive |

No hardware has been allocated or verified. Witnesses must be outside the lab
host administrator, hypervisor snapshot, credential, backup/restore and power-loss
failure domains. Two services on the same host or two accounts controlled by one
operator are not independent. Hardware-backed keys may protect key extraction;
they do not prove an uncompromised operator or correct monotonic storage.

## Threat model and proposed guarantees

Guest processes, lab operator, gateway and transport may be malicious. A local
privileged lab host administrator can forge guest observations, replace VMs and
roll back all local state. Native handles/ACL/SID checks do not resist that actor.
External evidence is useful only to the extent its independent collectors and
trust roots remain outside that actor's control. Host compromise is STOP, not
an invitation to infer safety from matching guest metadata.

| Threat / fault | Required design response | Current evidence / limit |
|---|---|---|
| Replayed signed receipt | Bind lab/run/node, plan digest, challenge nonce, epoch, expected prior anchor, time policy and signer; single-use acceptance | NOT_IMPLEMENTED; valid signature alone is insufficient |
| Stale trusted time | Independent authenticated time origin, nonce-bound response, uncertainty/deadline policy; reject clock reversal/unknown delay | UNVERIFIED; RFC 3161 time assertion alone cannot prove live arrival |
| Split brain / competing consumers | Independent durable compare-and-set reservations, fenced epoch, exactly one logical acceptance; 2-of-2 consistency | NOT_IMPLEMENTED; two witnesses are not a Byzantine quorum algorithm |
| Partial commit / power loss | Persist record before ACK, distinguish reservation/commit, reconcile both ledgers; uncertain outcome remains blocked | No real store; current replay/crash model is an abstraction only |
| One witness rolled back | Detect ledger/epoch disagreement against other anchor and retained receipts; stop, investigate, no automatic repair | NOT_IMPLEMENTED |
| Both witnesses and archive rolled back | External surviving monotonic root needed; correlated rollback may otherwise be indistinguishable | UNRESOLVED; never claim prevention |
| Compromised operator / key substitution | Two separately controlled roots, authenticated enrollment, explicit key rollover/revocation history and dual review | UNVERIFIED; test keys and placeholder owners are not enrollment |
| Gateway censorship / substitution | End-to-end verification and independent endpoint identity; timeout is BLOCKED; no fallback signer | Gateway can deny service; common transport does not prove independent observations |
| Shuttle injection / stale import | Quarantine parser, fixed bounded content, no autorun/executable import, chain-of-custody and independent receipts | UNVERIFIED; manual handling cannot supply live freshness |
| Forged PASS / self-attestation | Separate author, collector, reviewer and operator; audit source, exact SHA and receipt digests; metadata never grants authority | Inert checker always BLOCKED; native evidence remains UNVERIFIED |

Trust-chain audit must retain independently signed enrollment/revocation history,
time policy/version, collector identity, challenge/receipt digests, epoch, prior
anchor, custody transfers, exact candidate SHA and both review decisions. Never
publish secrets or identifying network details. Hashes authenticate contents only
when anchored to independently trusted provenance. No custom cryptography is
implemented here; future signatures require a reviewed standard library/protocol.

## Inert configuration contract

`lab-witness.example.json` and `installer.lab_witness_design` form a closed schema
version 1 for this decision record, not a deployment API or schema-2. The example
is the canonical allowed shape; choice may be UNSELECTED, A or B. All other values
are fixed safe proposal tokens. Unknown fields, endpoints, hostnames, CIDRs,
wildcard routes, commands, paths, missing/reused owner or key domains, fabricated
approvals, native PASS, altered base SHA and non-false authority flags are invalid.
Strict bounded JSON parsing rejects duplicate keys, non-finite values, excessive
nesting, invalid Unicode and wrong types. No input is echoed in diagnostics.

`manifest_valid=true` means shape-only acceptance. All results remain BLOCKED,
L1 NO-GO and physical NO-GO. Unknown resource identities, unresolved PGDATA,
unverified time/anchors and absent two-owner review are explicit blockers. Even
choosing A/B does not clear them. Real host/CIDR/SID/key values must not be inserted
into this public prototype; a future private enrollment contract needs review.
No endpoint probing, filesystem/resource existence check, native identity query,
key generation, network, durable storage, approval processing or execution exists.

PGDATA remains blocked: PowerShell layout `<parent>\<run>_<node>\postgres\data`
differs from adapter schema-1 `<parent>\<run>\<node>\pgdata`. No path rewriting,
manifest editing, adapter bypass, schema-2 enablement or compatibility claim is
allowed. A future versioned mapping must bind both intents and native identities
and pass adversarial cross-contract review before any L2 activity.

## Resources and human decision gates

Both variants require a dedicated approved host/OS/hypervisor, isolated guest
storage, two independent observer/witness owners and devices, separate key/root
custody, independently retained ledgers, trusted time origin, protected archive,
documented recovery authority and a STOP custodian. A additionally needs media
and quarantine custody. B additionally needs a dedicated deny-by-default gateway,
non-production transport and independently reviewable egress policy.

L1 pass criteria (not met): explicit human A/B choice; two independent owners'
formal review of assumptions, resource/failure domains, time/freshness budget,
anti-rollback limits, recovery and PGDATA mapping; validated versioned private
resource plan; no unsupported native claims. Automated tests validate only this
inert proposal. A later L1 GO would still not authorize L2.

Before L2, humans must privately prepare:

1. Hardware, supported Windows/Hyper-V builds, dedicated ownership and storage
   inventory, quotas and disposable scope; no names alone as proof of ownership.
2. Explicit A/B decision with signed two-owner review and accepted availability /
   freshness limitations; approved network/media boundary without production access.
3. Two external witness devices/admins/key custodians, independent time origin,
   durable ledger design and surviving anti-rollback root, including correlated
   rollback and full loss procedures. No live guarantees until separately tested.
4. Reviewed PGDATA mapping/protocol and pinned release/dependency provenance;
   schema-2 stays off until its own future authorization and safety proof.
5. Reviewed collectors for SID/ACL/token/handles, custody archive and exact evidence
   requirements for all twelve existing NOT_RUN VM scenarios; no synthetic PASS.
6. Recovery, STOP, rollback and removal runbooks; preserve journals/WAL/anchors,
   never infer ownership or automatically delete resources or downgrade migrations.
7. Separate explicit L2 provisioning approval, then distinct L3 read-only identity,
   L4 adversarial and L5 canary approvals. No approval is granted by this document.

Owner input checklist for GitHub: provide only symbolic resource classes,
availability, independent custody roles, A/B preference and unresolved policy
questions. Exchange real devices, private IPs, SID dumps, enrollment records and
keys only through an approved private channel; never request or post secrets.

## Recovery and stop policy (design only)

STOP on missing/disagreeing witnesses, unknown epoch or time, interrupted commit,
expired challenge, custody break, key revocation, ambiguous identity or host admin
compromise. Retain evidence; do not retry acceptance using the old challenge.
Two independent owners reconcile ledgers and retained signed receipts, revoke
uncertain authority and establish a fresh externally anchored epoch. Restoring a
VM checkpoint never restores permission. If no independent surviving anchor
exists, declare continuity unprovable and require new enrollment and explicit
human authorization. Do not erase the discontinuity or call it seamless recovery.

Removal is a future separately approved ownership-verified operation: no automatic
cleanup of media, guest storage, keys, journals or external anchors. External
history must survive lab teardown. No operational command is provided or run.

## Offline evidence scope

New tests cover malformed JSON/types, unknown/production resource references,
wildcards, missing/shared custodians, fabricated time/anchor/native evidence,
approvals, premature execution, schema-2, PGDATA mismatch and implicit selection.
Existing L0 and SID-binding regressions remain mandatory. Hosted CI checks exact
HEAD on Windows/Ubuntu Python 3.11/3.12 with zero skips/xfail/errors/failures and
retained JUnit. Inherited infrastructure workflows are excluded for this branch.
These results cannot establish native SID/ACL/handle behavior, physical isolation,
durability, trusted time, independent ownership or deployment readiness.

References: [L0 design](LAB_COMMISSIONING_PLAN_DRAFT.md),
[risk register](LAB_RISK_REGISTER.md),
[RFC 3161](https://www.rfc-editor.org/rfc/rfc3161.html).
