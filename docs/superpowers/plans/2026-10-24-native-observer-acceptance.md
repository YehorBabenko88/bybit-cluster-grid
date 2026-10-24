# Native observer independent acceptance plan

Baseline PR238 116bc11bb4c661c8b77be69c64b88f48a529968a. Own existing PR branch only.

1. Reproduce CI expected-refusal exit leakage. Freeze explicit case IDs and exact-HEAD evidence contracts before implementation.
2. C# read-only observer: strict local path contract; retain root and parent handles with no share-delete; use relative NtCreateFile with no-follow, identities, disk/directory types, reparse/hardlink rejection. Read owner/group/DACL via GetSecurityInfo on handles; native AccessCheck uses duplicated effective token, never manual permission arithmetic. Unsupported/malformed/token-uncertain paths BLOCKED.
3. Read-only re-observation must detect descriptor/identity drift. Held handles constrain rename but do not exclude all old writers, privileged admins or ACL changes. Global authority always false.
4. Pure negative tests for malformed structures, unsupported ACEs/types, deny-only groups, API failures and evidence forgery. Hosted GUID native tests per PS5.1/7: chain, junction/symlink/hardlink, parent replacement, effective group deny/allow, dangerous rights, denied APIs and deterministic drift. No native execution locally.
5. CI: pinned actions/exact HEAD, frozen inventory, JUnit/JSONL/source+binary SHA256, required aggregate rejecting missing/skipped failures. Preserve inherited general workflows and planning branch exclusions.
6. Independent adversarial review and fixes. Separate transaction-executor design only: durable authenticated append-only journal, barrier ordering, stable handle receipts, crash recovery, no automatic unsafe rollback. Apply never enabled.

Physical PC4 0/10 NOT_RUN. Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO.
