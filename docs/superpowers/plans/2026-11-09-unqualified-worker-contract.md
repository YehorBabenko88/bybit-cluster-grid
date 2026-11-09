# Unqualified worker registration contract plan

Root authorized pure contract/schema work and namespace allocation, not native
writes. Use existing isolated owner branch from539; preserve published history.

- [x] Commit six contract tests; observe missing-codec RED and preserve raw log.
- [x] Implement pure DATA codec plus closed acyclic intent and record schemas.
- [x] Record source identity separation, Root custody and UNKNOWN/retry decisions.
- [ ] Run fresh primary source/OID/raw guards and six pure tests; no Consul RPC.
- [ ] Independent review, publish minimal proposal Draft PR, send exact hashes.
- [ ] Obtain A5 identity-field ACK and Root final freeze SHA before native writes.

No transport/Core/runtime/worker/storage/UI changes. No new consensus, ledger,
broker, positive worker identity or resource capability. Native implementation
is a separate stage after exact custody/one-shot/session-policy decisions.
