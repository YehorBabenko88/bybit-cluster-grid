# Native fixture transaction continuation

User-authorized scope: PR #238, issue #243; no LS5/PC4 or production Apply/Rollback.

Architecture decision: implement a separate test-only .NET executable, not a new observer mutation switch. It creates its own GUID subtree with a protected DACL at native creation, retains root/target/journal handles, and changes only a single newly created file's DACL by handle. Production executor remains DESIGN_ONLY. Hash chaining is corruption detection, not authentication or durable anti-rollback. Recovery tests use explicit simulated crash barriers and refuse uncertain state.

- [x] Reproduce observer/evidence gaps with failing pure tests; correct schema, identity and privilege bounds.
- [x] Add hosted writer/delete-handle/descriptor and namespace race observations. Preserve effective-rights BLOCKED.
- [x] Test-first journal transitions and strict parsing in the separate fixture project; implement native create/set/flush/readback and recovery classification. No caller-supplied target path.
- [x] Bind all JUnit to head/run/attempt; independently check existing #242 artifact format and document #239 immutable handoff gaps without claiming implemented provenance.
- [x] Compile managed code locally without invoking native APIs; run Python/static/AST gates; publish once coherent.
- [ ] Run exact-head hosted Windows matrix, download/re-hash artifacts if generated, fix actual failures. Queued jobs never count as acceptance.
- [x] Obtain fresh source-only adversarial review; publish exact facts and remaining blockers.

Verification ledger: 197 Python tests passed (67 observer/evidence + 130 inherited ACL), 42 pure observer cases and 30 journal-model cases passed via managed-only reflection. Roslyn compile, actionlint, compileall, diff-check, PowerShell 5.1/7 AST parsing passed. Initial six nested-schema negatives were RED; phase-aware post-APPLIED rollback negative was RED; snapshot replay was RED, then fixed. Independent AI source review confirmed two P2 fixes (data sharing probes and phase-aware recovery); no further concrete defect found. No native API was executed locally. Hosted acceptance remains pending runner assignment; never infer PASS from this ledger.

Ruling: keep the frozen original native cases and extend the inventory explicitly. Failure injection is labelled and cannot count as real privilege removal or power-loss evidence. No cleanup outside newly created disposable CI resources; retain fixtures. Do not cancel other agents' workflows.
