# PC4 security acceptance plan

Baseline PR234 a55b6025c1f2d18d234d0f69348e2b0d55857358. Own branch
audit/pc4-security-acceptance-20261023, rebased onto the current PC4 base without
editing that branch; its two LSA commits remain content-identical.

1. RED/GREEN: synthetic native token-buffer bounds and group attributes; no live
   token reads, account operations or physical tests.
2. Move Cleanup refusal before all host observations and remove unreachable
   path-based deletion. Specify handle-relative deletion proof obligations;
   authorization remains false. Execute stays blocked pending physical review.
3. Bind child observations to retained process handles; model cooperative stop,
   launch failure, identity mismatch, timeout and unknown completion offline.
4. Independently validate synthetic JSONL/JUnit/run/head/hash evidence without
   accepting it as physical attestation. Add scoped hosted CI and receipts.
5. Parse/test pure code on PowerShell5.1/7 and Python3.11/3.12; publish own Draft PR
   and exact-head evidence. No infrastructure operations or merge.
