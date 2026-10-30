# Hosted Windows transport experiments: boundaries and acceptance

These are explicitly separate experiments in PR244, not an alternate Grid
acceptance path. No physical lab VM is selected. LS5/PC4 are not accessed. All20
physical G1 phases remain BLOCKED/null argv, Physical0/10 NOT_RUN, Execute/Cleanup
NOT_AUTHORIZED, Deployment NO-GO.

## Stock-only TCP reproducer

`tools.transport_reproducer_bundle` packages stock setup-python executables,
DLLs and stdlib plus the exact Git blob of `windows_transport_probe.py`. It has
no Grid source, site-packages, requirements, asyncio or Grid configuration.
The existing native custody/token/Job/loader boundary is deliberately reused;
this is independent of Grid runtime components, not an independent implementation
of Windows security APIs. A separate closed manifest and input directory prevent
accidental reuse of the Grid payload. Driver and pth contents are rechecked by
the offline evidence validator against exact Git blobs.

Parent retains literal IPv4/IPv6 listeners and exclusive bound-nonlistening
sockets. Host control connect/accept share a three-second cancellation budget,
before and after child execution. Concurrent accepts are armed before Resume,
then cancelled and joined on all guarded paths. Unexpected accept is not assumed
to authenticate its peer. Backlog4, endpoints, readiness times and control results
are recorded. A complete TCP handshake normally does not require application
accept; this is a controlled diagnostic experiment, not an asserted cause.

Child independently attempts both listeners, both nonlisteners and two fixed
documentation destinations (`192.0.2.1:9`, `[2001:db8::1]:9`). These are not trading
endpoints. Each attempt has the existing six-second deadline, implicit OS-selected
binding as in the original failing probe, nonblocking `connect_ex`, bounded select
readiness history, and `SO_ERROR` only after readiness. Zero without a verified
peer is not success. Endpoint-query failures retain the original connect fact.
Same-child v4/v6 TCP and stock socketpair exchanges are separate positive controls.

Actual suspended process PID/creation time, image, token user/groups/elevation/
integrity, AppContainer SID/count, TokenHasRestrictions and Job membership/limits
are read back. TokenHasRestrictions is observed0/1; the name CreateRestrictedToken
does not justify assuming a restricted-SID list exists. Parent elevated identity
does not establish ordinary-user isolation.

Bounded read-only GetExtendedTcpTable snapshots export only owned parent/child
PIDs and approved literal/wildcard local and loopback/documentation remote
addresses. Excluded owned rows are counted; completeness means API buffer decoding,
not total system activity or authenticated packet origin. Background sampling
does not touch process/image handles; held identity is checked around sampling.
PID/nonce/UTC correlation is not a trusted clock or durable replay protection.

## Explicit one-way pipe capability prototype

This is a new, narrowly granted IPC capability, never a transparent TCP fallback.
An independently staged stock-only driver has no network or Grid imports. Parent
creates a fresh anonymous pipe with a protected three-principal DACL, requests a
low MIC label, and passes only the write endpoint through the existing exact
handle list. Stdout/stderr alias that one endpoint; stdin is null. Parent read
endpoint is noninheritable and parent drops its write copy before Resume.

Child must observe numeric Win32 ERROR_ACCESS_DENIED5 for reading its write-only
endpoint, reading parent process memory and opening an existing synthetic foreign
canary. No canary data is read even if an unexpected open succeeds. Only then may
it emit one length-prefixed, canonical, at-most512-byte payload: `verb=ping` bound
to exact HEAD/run/attempt/nonce/PID. Parent accepts only exact expected bytes and
EOF. There are no requests, replies, subprocess verbs, paths, destinations,
credential operations or network proxy. An extra/truncated/replayed-context frame
is rejected. The offline validator independently checks frame and three denials.

Pipe DACL readback is checked; low MIC is requested but explicitly LABEL_UNVERIFIED.
Actual inherited-handle granted access is NOT_INDEPENDENTLY_QUERIED; successful
write and refused read are narrower observed facts. This is not independent owner
authorization or full process-lifetime attestation.

PeekNamedPipe/ReadFile use synchronous handles. Sole-reader polling bounds ordinary
collection, not a stalled kernel call. Unfinished reader resources are retained,
never reclaimed by path/PID. The disposable hosted process/VM supervisor remains
the outer failure boundary; no physical hard-deadline, crash recovery or cleanup
proof is claimed. The prototype is not yet a Coordinator/Worker adapter.

## Evidence and gates

All new native results and diagnostic summaries remain BLOCKED. One blocked JUnit
case (failure1, errors0, skips0) records the unclosed policy/authorization question.
Collector success means only a consistent BLOCKED witness was indexed; incomplete
controls/token/TCP/frame observations fail collection. It cannot satisfy or replace
the existing mandatory17-case Python containment gate. Debugged and undebugged
receipts are distinct; undebugged execution has no loader proof.

Original artifacts include exact native binaries, input/driver pins, native/child
JSON, JSONL, JUnit and SHA256 source/member indexes. Hashes prove consistency within
the stated trusted CI context, not malicious-producer resistance or physical
attestation. All files are rechecked against their exact source SHA; no predecessor
PASS is inherited. Failure-slot diagnostics contain only fixed stage/reason codes
and bounded numeric errors, never environment values, exception text or traceback.

Read-only ETW provider metadata is inventoried to avoid inventing GUIDs/event
schemas. No ETW session, packet capture, filter, exemption or capability expansion
is enabled. Missing causal events remain UNKNOWN. A later capture needs unique
session ownership/query/stop, approved schemas without secret payloads, finite
buffers/time, event-loss detection and safe teardown. Zero WFP events is not proof
that no filter blocked a connection.

## Remaining design choices

| Candidate | Evidence required before acceptance | Current limit |
|---|---|---|
| Raw AppContainer TCP | Causal tuple/process/filter evidence plus only-approved positive routes and all forbidden-route negatives | Original listener timeout UNKNOWN |
| Anonymous directional IPC | Exact handle distribution, bounded grammar, crash/EOF, no extra handles or proxy authority | FIXED_PING prototype only |
| Named pipe | Windows AppContainer/package/LOCAL support, exact DACL, client identity and impersonation revert | Not assumed cross-container merely from ACL |
| Restricted process + Job | Effective file/process/secret and network policy; Job alone is not network isolation | Existing fixture checks only |
| Network broker | Independently authorized verbs/destinations/credentials and denial of arbitrary forwarding | No network broker implemented |
| Separate VM | Selected disposable topology, independent identities/storage/network/time/witness controls | NOT_SELECTED |

Authenticated owner key enrollment, exact host/resources, external durable
anti-replay/anti-rollback/trusted time and reboot-safe custody remain P0. The
existing owner/replay preflight models are still always BLOCKED; neither HashSet,
local journal hashes nor a matching nonce are promoted to external durability.
No real Coordinator/Worker containment acceptance follows until transport is proven.

Source rollback is reverting the new source commit in its own branch. There is
no physical installation, ACL, PostgreSQL, service or release change to roll back.

## Comparison limits

The stock driver omits the original Grid probe's explicit DLL-directory setup
and uses nonblocking connect_ex/select diagnostics; parent accept is armed before
resume. These are deliberate experimental differences, not an isolated single-
variable root-cause proof. A different outcome requires a further controlled
comparison. TCP table samples correlate held pre-resume PIDs but do not attest
identity for every sample; monotonic ticks are not independently trusted time.

Class21 TokenHasRestrictions is recorded only as bounded raw bytes and returned
length (1 or4), with has_restrictions=null. The published DWORD contract and
observed one-byte hosted return disagree; neither raw value is interpreted as
a security guarantee. This diagnostic is separate from unchanged actual SID,
elevation, integrity, zero-capabilities and Job gates. Other sizes remain BLOCKED.
