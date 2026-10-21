# LSA JSON consumption boundary plan

**Goal:** keep all `grid-lsa-readonly-1` results diagnostic-only and physically BLOCKED.
**Architecture:** standalone pure Python text validator and stdin/stdout CLI, reusing
the existing bounded JSON parser. No integration with execution paths. Existing
producer/native API and physical harness remain byte-identical to Draft #223.
**Tech stack:** Python 3.11/3.12 hosted matrix, pytest, PS5.1/7 PlanOnly compatibility.
**Spec:** user task and docs/PC4_LSA_REPORT_CONSUMPTION_CONTRACT.md.

## Constraints and review focus

Separate branch/Draft PR from exact a2cff9b81bb460a022df785586fc2c300c99590e.
No CollectLocal, host connections, physical tests, ACL/account/service/policy changes,
merge or deployment. No automatic execution path or authority adapter.
Check duplicate/missing JSON keys, contradictory status pairs, exact booleans,
partial inventory, cleanup errors, unknown schemas/states, mock-to-physical laundering.

- [x] Search every tracked baseline file for all five requested fields plus producer paths;
      classify actual JSON consumers separately from unrelated authority fields.
- [x] Add failing CLI regression showing the missing standalone validation boundary;
      implement strict shape/type/invariant checks and permanent BLOCKED output.
- [ ] Pin negative test inventory; add specialized CI receipts and PS5.1/7 producer
      PlanOnly compatibility through the new CLI. Preserve all baseline mock suites.
- [ ] Independently review changes, record defects vs coverage gaps, commit/push separate
      Draft PR and verify final exact-head CI/downloaded receipts and unchanged sources.
- [ ] Export report, source-search inventory, commit SHAs, receipts and GO/NO-GO matrix.
