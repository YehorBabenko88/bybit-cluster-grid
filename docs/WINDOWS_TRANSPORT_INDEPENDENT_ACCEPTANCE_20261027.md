# Independent Windows transport and physical G1 acceptance — 2026-10-27

**Integration exact HEAD:** `ee00718c8574fc5cf5e3678810acce4464f158ae`  
**Integration tree (coordinator report):** `3f2889a096d298781df1cb26d900b5e9d6c3a2bf`  
**Verdict:** `ISOLATED_E2E_PASS` (Linux only), `HOSTED_NATIVE_PYTHON=BLOCKED`, `WHOLE_SYSTEM=PARTIAL`, `PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION=BLOCKED`.

## Independently executed original ZIP verification

Read-only checker executed against **original** GitHub downloaded ZIP bytes, not producer output. It validates ZIP CRC/path/duplicate entries, pinned outer SHA256, context, all included manifest file hashes, JUnit failures/errors/skips, and E2E JSONL count. A changed ZIP byte and JSONL modification with recomputed internal manifest SHA both differ from the independent external digest.

| Original artifact | Run / attempt | Raw SHA256 | Independently checked |
|---|---|---|---|
| 12751871326, 47,849 bytes | 40541132457 / 1 | `0071719dadef675b49b8a2c0f65afaf9689e508aecade27deb52e29dc4f5179d` | 11/11 included manifest files; 26 E2E +32 PG18 JUnit cases; 26 JSONL rows; zero failure/error/skip; core isolated PASS, whole system PARTIAL |
| 12749704044, 18,965 bytes | 40541131601 / 1 | `79c45ad1afddfbbb33266a3e24478312e44ff2db29ff4578c1cd2ec11c53fa10` | 4/4 included manifest files; 32 PG integration +12 baseline +12 candidate rejection JUnit cases, zero failure/error/skip |

**Limitations:** Not all source hashes independently matched to immutable Git blobs; rehashed archive plus compromised external trust anchor is not defeated by SHA256 alone. No physical host execution or Windows Python/Grid startup accepted.

Full-system workflow `40541132457` **FAILURE**: four Windows Python containment matrix jobs plus required Python and first-boot gates failed. The Linux PG18 job and four offline matrix jobs succeeded. Native controller/observer/G0 LSA fixture gates succeeded, but cannot substitute for Python containment.

## Windows network P0 — evidence and required reproducer

- Parent host IPv4/IPv6 socket, bind, listen, connect and accept positive controls passed. Child own IPv4/IPv6 socket/bind/listen and same-child TCP send/receive, socketpair, and Proactor construct/close passed.
- Debugged and undebugged child-to-parent host-loopback `connect` timed out; nonblocking accept observed WSA10035. A later WSA=0 is **not** the error from the failed connect. WFP exported no own-GUID drop; absence of an event is **not** absence of a blocking policy.
- **Required deterministic test:** prepare a held, bound/listening host socket and record address family, sockaddr, backlog, socket owner, listening start monotonic time, child launch time, deadline, exact connect exception and WSA code at failure, accept attempts, cancellation, pending socket count and both endpoint identities. Run four isolated variants: IPv4/IPv6 × debugged/undebugged. Include negative controls: listener absent (refused), intentionally blocked (only if disposable and explicitly authorized), saturated backlog, wrong family/address and early listener close. Never classify a timeout as WSAEACCES or a specific WFP filter without causal evidence.
- **Required source contract:** no inherited host socket or broker capability can be silently introduced; any future broker/pipe/TCP design must have independent identity and authorization tests, not just localhost success.

## Transport architecture acceptance choices

| Option | Boundary | Required independent PASS evidence | Status |
|---|---|---|---|
| AppContainer capability | AppContainer token, declared capability SID, firewall/WFP, destination | Explicit owner-approved scoped capability; denied external/production endpoints and positive only intended loopback; effective token and WFP provenance | NOT_AUTHORIZED |
| Brokered IPC | Privileged broker vs low child | Broker authenticates client token/SID and exact job/process/permit; strict operation allowlist, bounded messages, no arbitrary proxy, no inherited production credentials; impersonation revert on all failures | DESIGN_ONLY |
| Named pipe | Kernel pipe ACL + server/client impersonation | Effective DACL, reject unknown SID/reparse and duplicate pipe name, verify impersonation token per request, prevent impersonation leakage and privilege confusion, timeouts/cancellation/cleanup | DESIGN_ONLY |
| Restricted TCP | Loopback or private tunnel + firewall | Held listener identity, authenticated peers, no wildcard bind, port collision rejection, denial of external and production routes, exact socket lifecycle and replay limits | BLOCKED |
| Job + restricted token | Process tree/handles/DLL closure | Active-process limit, child creation refusal, handle list and process image identity, low integrity/admin deny-only, no arbitrary DLL/import/child escape | HOSTED_FIXTURE_ONLY |
| Tailscale/SSH | Host overlay and remote identity | Independently verified pinned host identity, tailnet grants, approved source/destination, authenticated tunnel, no inherited PG DSN or production routes | PHYSICAL_NOT_RUN |

## Physical P0 contracts and negative tests

1. **Owner authority:** independently pinned owner public key and signed exact HEAD/tree/host SID/ports/PGDATA/run/expiry permit; reject wrong key, replay, host mismatch, expired and scope-expanding permits. CI test keys are not owner keys.
2. **Durable replay/rollback:** externally witnessed consume-before-effects anchor surviving reboot and coordinated local rollback; test simultaneous rollback of local checkpoint+journal; must reject, not re-authorize.
3. **Process custody:** held process/job handles, immutable image/source hashes, PID+creation time and token identity; reject PID reuse, foreign process, unknown child, handle loss and cleanup after reboot. Retain unknown resources.
4. **PGDATA and roles:** read-only independent effective ACL, principal and DB identity, no inherited production DSN/credentials; reject existing 5432/55432 or ambiguous PGDATA and SQL mutation before separate approval.
5. **Cleanup:** explicit separate owner cleanup authorization, durable intent, exact owned GUID and handle identity, STOP on any uncertain journal, marker or descendant; never adopt by path/PID alone.
6. **Secrets and trade safety:** deny production Bybit credentials, endpoints, trading execution and outbound routes; inject synthetic canary and verify no access, no logging, no exfiltration.

Physical G0 is not independently complete. All 20 G1 phases remain `BLOCKED` with `argv=null`; PC4 SID/ACL 0/10 NOT_RUN; Execute/Cleanup NOT_AUTHORIZED; Deployment NO-GO. **Do not execute G1.**
