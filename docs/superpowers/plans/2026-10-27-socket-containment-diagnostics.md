# Windows socket containment diagnostics plan

Execute inline; user authorizes autonomous source/hosted work, no physical G1.

Design: preserve zero capabilities/atomic Job/restricted token. Child records each socket/bind/listen/connect/accept operation on IPv4/IPv6 loopback, bounded timeout, exact exception type/numeric facts. Post-exception WSAGetLastError is labelled non-authoritative. Parent independently proves its own IPv4/IPv6 listeners via connect/accept controls. Unknown remains BLOCKED. Never infer policy denial from timeout/refusal. Read-only hosted firewall/BFE/loopback-exemption metadata is diagnostic only.

- [ ] Red/green tests for socket exception classification and no unknown-to-PASS conversion.
- [ ] Add child trace and native parent positive controls, receipt/schema bindings.
- [ ] Run offline inventory/static checks; commit/push PR244 only; inspect original exact-head matrix artifacts.
- [ ] Fix only demonstrated root cause, retain security gates; independent review/GPT4 evidence.
- [ ] Prepare owner/durable/reboot/cleanup separately, never enable physical authority.
