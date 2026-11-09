# Failed context entry cleanup — explicit LOCAL successor

A8-F28 P2 owner correction candidate. A5 source review first identified that
19fa `__enter__` could raise before `__exit__` was registered. A8 and A5 then
independently reproduced open owned DB/lock descriptors and a denied contender
until caller manual close. Prior normal-path12 PASS remains valid; it did not
exercise failed entry and is not reclassified as unconditional cleanup proof.

This separate successor stacks onto explicit proxy Coreb0/3dd; old19fa/b0
sources remain immutable. Only runtime change fromb0 is `__enter__`: if its
ownership guard raises, close ONLY the instance's retained own descriptors,
retain the original error/traceback, add a cleanup note if close reports failure,
then rethrow. No persistent DB or lockfile is deleted. Close stays idempotent;
no native RPC/session/registration/job/resource/effect path is introduced.

Actual new test method constructs/retains an owned Journal, changes its path
before `with`, proves the body did NOT execute and both descriptors are closed,
then an OWN child acquires the valid original file WITHOUT caller/manual close.
Original Journal rows remain unchanged. Another actual owned sidecar fault
exercises a pure close-report failure after actual close: original entry error
and note survive; removing ONLY the known test sidecar lets another OWN child
acquire without manual parent close. Bounded children return0; they are local
filelock tests, not native PID identity/worker/enrollment proofs.

Initial focused owner RED on sourcebbd1e02e fails with actual contender DENIED
instead of ACQUIRED; it is an owner-checkout partial provenance run, not a fresh
whole-source-qualified RED. That log is preserved separately. Fresh exact-source
13-method local qualification must rerun all prior12 plus this method; four
bounded own child calls are included in those13, not extra test PASS counts.
The same exact successor also runs the separate2-case proxy-free actual Consul
READ qualifier; no prior Core2/local12 count is transferred. Logs/source closure
are reported separately. No registration native write qualification is run.

The fixed local API and record schemas are unchanged; filelock/Journal remains
local single-writer/non-authorizing. Root role/private path/ACL/lifecycle and
exclusive authority/client/config ownership remain explicit prerequisites.
Actual source/API review and Root/A5 custody ACK plus independent A8 acceptance
remain gates; no automatic P2 closure/adoption merely from this proposal.
Core3dd F27 correction is unchanged but independently reviewed on its own and
this paired source as requested, not a silent replacement of old868 pins.
Mandatory hosted/Linux/physical qualification and positive native APIs remain
unfulfilled. Publicsubmit DENY, registration/effect grants false, NO-GO.
