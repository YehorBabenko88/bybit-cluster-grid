# Integration cycle246 and native G1 controller fixture plan

> Execute inline using systematic-debugging/TDD; existing user specification authorizes source/hosted work, not physical G1.

Goal: selective parser correction, exact compatibility/CI diagnosis, and real disposable
Windows-native proof of controller primitives without enabling any physical phase.

Architecture: a separate CI-only executable reuses the native handle/NTFS fixture
primitives. RSA-PSS/SHA256 uses platform crypto and externally supplied pinned public
key in tests; fixture-generated private keys are NEVER physical authorization.
Process launch is suspended, AppContainer capability-free, assigned to an unnamed
kill-on-close/non-breakaway Job before resume, and checked through held handles.
Only fixed Windows test tools/constant argv are accepted. Existing files/DBs/services
are never adopted. Journal and root are retained; deletion is bounded to the created
marker handle after exit and identity checks. Profile storage remains disposable CI
state: no unsafe profile-name deletion is introduced.

- [x] Read current244/246 and reproduce recursion in plain/-O Python within65536bytes.
- [x] Port only catch and regression paths;84network tests pass.
- [x] Download exact239/242 preflight failure logs; classify guards/signature, no missing imports in latest failures.
- [ ] Add pure signed permit/context/replay/state-machine fault tests before native effects.
- [ ] Add native Job/AppContainer/process-handle tests on hosted Windows GUID resources only.
- [ ] Journal flush intent before resume; guardian-held recovery barrier tests; no OS-reboot claim.
- [ ] Prove bounded marker cleanup refuses live/unknown child, stale permit or changed identity.
- [ ] Required reusable Windows PS5.1/7 gate, strict JSONL/JUnit/SHA256/exact source receipts.
- [ ] Freeze complete offline inventory; run compile/actionlint/offline and real hostedPG18/nativeCI.
- [ ] Refresh read-only G0 using already pinned owner-confirmed pc4 transport, no SQL/host changes.
- [ ] Publish compatibility matrix, raw evidence, terminal statuses and independentQA handoff.

STOP: AppContainer loopback exemption/WFP/firewall policy would be an infrastructure
change; never apply on LS5/PC4. Capability-free fixture is not a viable Grid transport
policy. Physical source/principal custody, trusted authorization key distribution,
external durable anti-replay anchor and crash/reboot recovery remain unproved.
All20physical phases stayBLOCKED. Execute/Cleanup/Deployment unauthorized.
