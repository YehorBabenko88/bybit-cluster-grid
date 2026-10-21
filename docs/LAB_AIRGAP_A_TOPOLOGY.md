# Air-gap A topology — proposed observations only

Status PROPOSED / UNVERIFIED. No physical or native inventory was performed.
Hardware, Windows build and Hyper-V version are OWNER_UNVERIFIED. Physical NO-GO.

```text
Dedicated disconnected lab host (unverified)
  Hypervisor management: local console only, separate privileged account
  Private virtual switch: CONTROL guest <-> WORKER guest (both uncreated/off)
  Dedicated guest storage and bounded disposable fixture volume (unallocated)
          |
          | future supervised outbound evidence only; no live network
          v
Owned export medium -> separate intake/quarantine -> offline observer archive
                                            -> independent observer A review
                                            -> independent observer B review
                                            -> STOP custodian evidence reference
No return path to lab. No external witness implied by this drawing.
```

All arrows are a design proposal requiring approval, not existing connections.
The external intake/review process has no route or shared storage into the lab.
Evidence receipts remain outside. Future return receipts/challenges would need a
separate inbound design/review and are disabled, including on the same media.

## Boundaries and future verification methods

| Boundary | Required design | Future observation by independent humans (NOT_RUN) |
|---|---|---|
| Host physical NICs | No production/internet/Tailscale connections; dedicated hardware; no alternate management path | Physical port/cable/adapter inventory, device configuration and independent review of out-of-band management |
| Wireless | No Wi-Fi/Bluetooth/cellular/tethering or USB network adapter | Physical/device inventory and configuration review; disabling an icon alone is insufficient |
| Virtual network | Private guest-only switch; no bridged/external NIC, NAT, routing, host adapter or default gateway | Independently reviewed switch/NIC/route/firewall topology and absence of dual-homed guests; no live probes at L1 |
| Host integration | No shared folders, clipboard, enhanced session, host mounts, drive redirection, shared credentials | Independent integration/device/VM configuration review; exceptions require a new approval and contract |
| Storage | Dedicated, explicitly owned guest/fixture volumes; no production WAL/backups/PGDATA attachment | Private ownership record, capacity/quota plan and future native volume/file/handle evidence |
| Management | Local console; host administrator separate from guest operator/adversary accounts | Private account/token/custody review, no remote management dependency |
| Intake | Physically separate quarantine device; no lab attachment or bidirectional media reuse | Owned media custody and device policy review; no automatic execution or mounting trust |

No actual hostnames/IP ranges are accepted in public proposal metadata. There is
no allowlisted lab egress in variant A. If any dependency needs Internet, DNS,
NTP, VPN, domain trust or a gateway, stop and revise the design rather than open
a route. Package/image intake is a separate supply-chain design; evidence export
does not authorize software import or installation. No installer is executed.

## Roles and separation

| Role | Proposed custody | Limits |
|---|---|---|
| Operator | OPERATOR_DOMAIN | Executes only later explicitly approved scope; cannot approve own evidence |
| Observer A | OBSERVER_A_DOMAIN | Independent capture/provenance review; no shared admin credentials with operator or B |
| Observer B | OBSERVER_B_DOMAIN | Independent security review and cross-check; not a second account under A's control |
| STOP custodian | STOP_DOMAIN | Can halt a trial; cannot alone resume, clear disputes or authorize new resources |

These four domains are symbolic and UNVERIFIED. Two human architecture/security
reviews must be independent of authorship and each other; role assignment does
not itself record a review. Reviewers disclose shared control, employment/custody
dependencies and conflicts privately. Observer independence from a compromised
host requires separately trusted collection/retention; a guest-exported log alone
is not independent observation. If this cannot be achieved, narrow the claim or
remain blocked. No real SID/token is queried by these planning tools.

## Minimum owner resource packet

Dedicated host capability/OS/hypervisor proposal; isolated switch/guest/storage
inventory; separate quarantine and evidence archive devices; dedicated owned
export media; operator/two observer/STOP custody roles; trusted roots and retained
history policy; quotas, recovery authority and physical STOP procedure. Actual
identities and sensitive device/network facts go through private review.
No resource is assumed exclusively Grid-owned from its path, name or service name.
