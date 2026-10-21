# Supervised outbound evidence process — design, not implementation

PROPOSED / UNVERIFIED; transfer authorization NOT_GRANTED. No media is accessed.
One-way means a supervised procedural export boundary, **not a hardware data
diode guarantee**. Removable-media firmware and human error remain attack paths.
No media/device is trusted because it contains a manifest or matching SHA256.

## Proposed custody flow (all future checkpoints)

1. Two humans verify exact plan/candidate SHA, scope, owned export medium and
   case/attempt identity before export. Export only bounded inert evidence files,
   never executables, scripts, links, archives with traversals or credentials.
2. A dedicated owned blank medium is allocated privately. Record its evidence
   reference and custody handoff; no auto-format, erase or reuse is authorized.
   The lab records hashes and independently reviewable collection provenance.
3. Separate intake/quarantine custodian receives the medium outside the lab.
   No autorun, macros or trust inheritance; future approved read-only handling,
   format/size/depth checks, safe filenames and malware/content review are required.
   Malware-negative is not proof of benign data. Reject symlinks, reparse paths,
   executable content, parser ambiguities, unexpected files and signature errors.
4. Check complete file inventory and SHA256 against authenticated origin evidence.
   Future standard-library signature verification must bind signer, domain,
   plan/candidate digest, run/case/attempt, sequence, prior receipt and content.
   Reject unknown/revoked/substituted keys, ambiguous encoding and incomplete chains.
   No production keys, signatures or trust enrollment are implemented here.
5. Observer A and B independently review custody and source facts, not merely
   each other's PASS. A proposed external accepted-ID ledger rejects duplicate
   attempts, conflicting same-ID contents, stale/unknown chain and disputed state.
   Ledger durability and monotonicity are NOT_IMPLEMENTED; do not claim otherwise.
6. Retain raw evidence, both decisions, rejects and external receipt in separately
   controlled archives with retention/capacity/corruption handling. Receipt state
   is PROPOSED/UNVERIFIED until genuine review. Missing review means BLOCKED.

Media never returns from quarantine to the lab in this phase. Do not reuse it for
software intake or receipt delivery. Archive copies do not authorize destruction
of original media or lab data. Physical disposition requires separate ownership
verification and approval. No automatic cleanup is provided.

## Replay, freshness and offline receipts

An exported receipt may identify an experiment but cannot grant permission to
execute it again. Exact duplicate and same-ID/different-digest receipts must be
rejected against independently retained history. A new random attempt identifier
is not proof of fresh underlying VM state. Host timestamps, nonces generated in a
rolled-back VM and copied signatures cannot establish live time or continuity.
No inbound fresh challenge exists in this one-way model. This limitation is an
explicit blocker for durable anti-rollback/freshness certification.

After power loss or uncertain ledger update, preserve both pending and committed
records, block acceptance, reconcile under both independent custodians and issue
no automatic retry. If all archives/anchors/checkpoints are rolled back together,
history may be indistinguishable; declare continuity unproven. File transport
does not instantiate a witness. No real durable ledger/crypto is added by L1.

## Public template and private record

`docs/lab-airgap-a/evidence-template.json` is an **empty design template**, not
native evidence or an accepted receipt. Fields requiring actual facts stay null;
all flags false; observations UNVERIFIED/NOT_RUN. It is never accepted as PASS.
Public PRs contain only symbolic/redacted references. Private future records need:

- Exact candidate/plan SHA, lab/run/case/attempt, collector identity/tool version,
  OS/hypervisor/VM image identity, start/end observations and clock uncertainty.
- Actual SID/token groups/privileges/elevation/integrity; ACL owner/DACL/inheritance;
  volume/file IDs, handles/share modes and final path; separate private provenance.
- Expected/actual operation, error/result, handle lifecycle, pre/post identity,
  race barrier and retained raw capture. No success inferred from a missing file.
- Artifact inventory/digests, custody handoffs, signer enrollment/revocation policy,
  previous receipt/sequence, two independent decisions and STOP disposition.

No secrets, private IPs, SID dumps or key material should be posted on GitHub.
Null/unknown fields mean no evidence, never inferred defaults or approval.
