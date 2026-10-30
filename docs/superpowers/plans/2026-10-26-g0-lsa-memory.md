# G0 SID-bound LSA observer and PATH diagnosis

Goal: prepare and independently review a memory-only policy reader; investigate SSH Process PATH without configuration changes.

Architecture decision: reuse read-only LsaOpenPolicy/Enumerate/Free/Close backend; add canonical expected/observed SID binding, strict result shape and explicit10-right map. Retain unknown effective rights/group completeness/readiness. Do not reuse CollectLocal Add-Type on PC4: compile reviewed .NET Framework DLL only on disposable hosted CI, verify its source/head/SHA externally and load bytes in memory. No physical package changes.

Alternatives rejected: secedit export writes host files; Add-Type creates compiler temporaries; logon/token-based evaluation violates scope. No token, logon, policy mutation APIs. Ordinary OS/SSH auditing is not controlled by the observer; no zero-OS-write attestation.

- [ ] Regressions first: zero-count/non-null native buffer, SID mismatch, malformed/noncanonical identity, API/AccessDenied/cleanup errors and incomplete identity inventory.
- [ ] New memory-only entry point: PlanOnly default; exact PC4/name/SID/source/binary binding; errors block. No native call before identity checks.
- [ ] Strict evidence validator: head/run, subjects,10rights each, numeric API results, duplicates and false readiness claims fail closed; JUnit/JSONL+SHA.
- [ ] Hosted PS5.1/7 and Python3.11/3.12 fake API tests; no real policy observation in CI. Build production-only DLL separately from test DLL.
- [ ] Read-only PATH observation: fresh no-profile SSH session, Process/User/Machine registry PATH, exact dollar-underscore fingerprints, OpenSSH shell settings and relevant config/profile references only; no general environment/commandline/secrets dumping.
- [ ] Independent source/adversarial review, exact-head CI and raw evidence; no G1 Execute/Cleanup, no account/ACL/service/SSH/PG/firewall mutation.

User authorization: autonomous source/CI and read-only PATH investigation, no physical mutation. A successful direct policy enumeration is never G1 authorization, effective-token proof, or physical SID/ACL PASS.
