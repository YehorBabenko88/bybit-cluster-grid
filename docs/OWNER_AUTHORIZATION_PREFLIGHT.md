# Offline owner authorization and reboot preparation

This preparation adds no physical execution or cleanup authority. It makes the
remaining authorization and recovery prerequisites explicit and testable without
opening a socket, reading host state, creating keys, or modifying a ledger.

## Existing contracts inspected

`installer/native-g1-controller-fixture/ControllerPolicy.cs` already verifies
RSA-PSS permits with an independently supplied public-key fingerprint, exact
permit binding, bounded expiry, and an in-memory nonce set. However,
`ControllerMain.cs` generates that RSA key and pin for each hosted fixture.
This is neither owner trust enrollment nor persistent replay protection.

Guardian binds the live fixture, child, retained file handles, and permit. Its
hash-chain journal uses `AppendFlush`; the independent-in-relation-to-journal
anchor is an in-memory string. `Recover` validates those retained objects at a
cooperative barrier. It cannot authenticate a reboot, restore handle custody,
or resist rollback of journal plus checkpoint. `OwnedChild.Cleanup` rejects a
live/unknown child, requires the guardian's exact fixture/child references, and
marks disposition through the held marker handle. None of this establishes
ownership after process death or reboot. Paths, PIDs, serialized file IDs, and
copied checkpoint strings cannot replace those live bindings.

`installer/vm_test_attestation.py` verifies Ed25519 signatures against public
fixture roots and uses process-local replay state. Its report stays
TEST_KEY_ONLY/BLOCKED. `installer/vm_replay_model.py` assumes validation,
atomic commit, trusted clock, and an independent nonrollback anchor. Its
correlated rollback counterexample remains applicable. Neither contract is
an owner-authenticated production verifier or durable anti-rollback service.

## Minimal executable preparation

`integration.owner_authorization_preflight.assess_preparation(raw,
expected_scope)` compares bounded JSON declarations with caller-supplied scope
metadata. This is a draft preparation record, not a signed permit format or
an authorization token. Both arguments are untrusted declarations. A matching
key fingerprint proves no key possession, protected enrollment, identity,
revocation status, or approval.

The exact scope contains `head_sha`, `artifact_sha256`, `owner_key_sha256`,
`host_id`, `session_id`, `boot_id`, and `action` (`execute` or `cleanup`).
The draft also requires integer `schema: 1` and `recovery` with
`previous_boot_id`, `current_boot_id`, boolean `handles_lost`, and nullable
`journal_sha256`/`anchor_sha256`. Current boot declaration must match scope.
UUID/digest syntax is checked; these values are never measured by this helper.
It reuses the existing bounded, duplicate-key-rejecting VM JSON loader.
Unknown fields, malformed data, and mismatched scope cannot promote readiness.

Matching scope sets only `metadata_matches: true`. All results retain
`status: BLOCKED`, `authentication: NOT_IMPLEMENTED`,
`durable_replay: NOT_IMPLEMENTED`, zero verified safety cases, and false
execution, cleanup, automatic-resume, host-verification, and readiness flags.
Matching journal and anchor hashes do not remove any blocker. Repeated calls
perform no replay consumption or persistent operation.

Declared reboot or handle loss produces `RETAIN_FOR_REVIEW`. Matching boot and
declared retained handles produces `NO_AUTOMATIC_ACTION`; it does not establish
that any handle exists or is trusted. No existing executor consumes this
report, and no CLI, signing API, storage adapter, or recovery callback is added.

## Required work before an owner-authorized physical path

1. Establish the owner identity and independently enrolled public-key pin,
   protected private-key custody, revocation policy, and trusted time source.
   Do not adopt the fixture key or accept a pin from the signed request itself.
   Select the real trust provider before implementing an owner permit protocol.
2. Bind separately scoped execution and cleanup authorization to exact code,
   artifacts, intended host/session/boot, operation and owned resource identities,
   nonce/sequence, expiry and policy/key epoch. A successful signature alone
   cannot authorize any effect. Revalidate authority immediately before effects.
3. Choose and verify the authoritative durable replay ledger and external
   monotonic/nonrollback anchor. Establish transaction/ack ordering, fencing,
   failure recovery, revocation persistence, and uncertain-commit behavior.
   A local hash chain, flushed file, or same-disk checkpoint does not establish
   independent anti-rollback. No such backend is selected or implemented here.
4. After reboot or handle loss, retain resources and require fresh authenticated
   owner authorization. Reestablish custody through a reviewed native recovery
   boundary; verify resource identities and child absence/exit using newly held
   handles. Old process/object references have expired. Until that boundary has
   real evidence, refuse resume, termination and cleanup. Do not reopen names
   and treat a matching PID/path as ownership proof.
5. Only after all preceding checks may a reviewed cleanup path act on the exact
   owned held resource handles. Unknown/live child, identity disagreement, stale
   fence, expired permit, missing anchor, truncated journal, uncertain commit,
   or correlated rollback evidence must retain resources for review.

These are implementation requirements, not implemented security guarantees.
No Windows reboot/power-loss experiment, privileged-admin resistance, real owner
signing, external anchor, LS5PC4 connection, SQL, ACL operation, or native cleanup
was performed by this preparation. Existing physical/G1 blockers remain.

## Verification

The pure tests cover metadata substitution (including owner-key fingerprint,
host/session/boot and execute-vs-cleanup), invalid/promoted fields, bounded JSON,
reboot/handle-loss retention, nonpromotion from journal/anchor hashes, and
nonmutation/repeated-call behavior. They provide no owner-authentication,
durability, or reboot evidence. Existing crypto and replay-model tests remain
separate and retain their original limitations.
