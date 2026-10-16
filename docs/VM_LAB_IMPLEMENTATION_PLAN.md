# Disposable VM Lab: implementation plan

Base: c99adbfa47dc0ce286e9dd8f966ba243cfd55b10. Goal: offline design and metadata checking only.
Architecture: pure strict JSON validator, immutable case catalogue and permanently blocked evidence report; no hypervisor/backend calls.
Tech: Python standard library, pytest, PowerShell5.1/7 JSON launcher, existing pinned Actions.

1. Write version1 design including modelA/B trust limits, resource/layout/image/approval contracts and preserve-only disposition.
2. Add failing tests for unsafe host/storage/network/credential/disk/account/approval/image/quota configurations and readiness promotion.
3. Implement pure validator with exact nested schemas and bounded JSON parsing, canonical identifiers/paths/SIDs, fixed safety flags, independent-principal catalogue.
4. Add PS5.1/7 compatibility validation, no probes or commands; integrate Python3.11/12 offline CI without altering existing runtime/native gates.
5. Run focused/full offline tests, syntax/actionlint, independent read-only review; commit/push NEW branch, create Draft PR, verify exact-SHA Actions and report limitations.

No real VM, guest account, storage, network, PostgreSQL, SQL or service operations. Future provisioning and attestation require separate review/approval, not a field in this plan.
