# Owned Consul client proxy isolation — explicit Core successor

Scope: A8-F27 P1 source-routing correction, not an incident/RCA claim. Root
approved this separate successor and own disposable READ-ONLY qualification;
old Core868, Grid539/19fa and Root034 pins/evidence remain immutable.

Only Core runtime change: the existing source-owned
`httpx.AsyncClient(verify=context, follow_redirects=False, trust_env=False)` now
explicitly ignores inherited environment proxy configuration. No new client,
authority, election, LAN transport or retry policy. Existing explicit TLS/CA/
client certificate configuration remains; no generic claim about every OS trust
source is introduced. Arbitrary injected clients are not modified or admitted:
they remain isolated-lab-only, `_owns_client=False`, caller-owned and not closed
by authority.close. trust_env=False alone on an arbitrary injected/proxied
client is NOT proof of a safe owned route.

Root and A8 observed Core868 default trust_env=True could capture proxy mounts
when created, even for an accepted literal loopback URL. Changing current env
after construction does not remove those mounts. This demonstrates a boundary
gap, not historical external egress, proxy use, credential leak or provider send.
No global environment, network/security/service or office-machine change occurs.

## Actual isolated regression

`tests/coordination/assignment_v1/proxy_isolation/test_proxy.py` launches ONLY
owned temporary Consul1.22.2/default-deny ACL three-voter servers and an owned
loopback HTTP proxy trap. Trap readiness is synchronized. It returns a bounded
empty403 response and records ONLY a count, never path/headers/ACL token/body.
Two bounded dedicated child interpreter calls use exact source and same pinned
environment. Proxy variables point ONLY at the owned trap in the CHILD env;
NO_PROXY is empty BEFORE client construction. The child removes those env
variables AFTER construction, then performs the actual consistent native
`GET /v1/operator/raft/configuration`. That post-construction removal cannot
repair old captured proxy routing and is not used as the admission criterion.

Old Core868 RED: trap count1, actual native read fails, owned trust_env=True;
the separate injected/no-request lifecycle check passes. New constructor must
yield actual three native voters/one leader, trap count0, owned=True,
trust_env=False, follow_redirects=False and owned client closed by authority.
The injected check sends NO request and confirms injected client remains
unowned/trust_env=True/not closed by authority, then explicitly closes its own
client. Neither case fabricates a Consul/session/receipt/permission response.

No session/create, job/registration KV or protected effect call is performed by
the test client. Authorized fixture bootstrap creates the disposable Consul
cluster itself. All retained own Consul processes, child calls and proxy server
threads are retired. No arbitrary external URL/provider is accepted as input.
Actual mandatory2 IDs and primary Git/raw inventory guards are in
`run_qualification.py`. Logs/before-after source maps are reported separately.
Initial owner-checkout RED is partial provenance; fresh primary RED5344b4cf is
qualified separately and must not be confused with that initial observation.

## Consumer custody and remaining gates

New consumers must pin the exact successor Core source and require the actual
owned exact AsyncClient/transport, `_owns_client is True`, trust_env=False,
not is_closed, captured same client/config identity before authentication and
the same actual authority across broker/native handler. Fixed constructor source
must establish no explicit proxy/mounts/redirect configuration. Entry checks
alone do NOT establish mid-await custody: Core reads self.client after awaits
and on endpoint attempts. Root must exclusively own authority/client/config
lifecycle throughout operation AND cleanup, with no supported concurrent
reconfiguration/close. Supporting that concurrency needs a separate per-request
source ownership contract; no hostile Python mutation defense is claimed.

Closed/injected/rebound-client consumer rejection belongs its separate exact
Root source qualification, not these two Core cases. Lost custody cannot use a
replaced/unknown client for cleanup; preserve original error and native-cleanup
UNKNOWN. Proposed local-only broker invalidation is another explicit source
successor, not implemented here or aliased onto old broker1f971.

RootRegistrationCustody local12 source qualification is NOT transferred to this
Core pair, and Core native25/Root16 predecessor PASS counts are NOT transferred.
A8 independent exact-source/actual-route qualification and Root explicit new
pair/adoption remain gates. No registration mutation qualification until actual
local custody/source/Root-A5 ABI and proxy-free client gates are captured.
Native grants/public submit remain closed, production/physical NO-GO.
