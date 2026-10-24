# PR244 selective compatibility checkpoint

Review inputs fetched and rechecked on 2026-10-24 (moving branches are not pins):

| PR | Exact reviewed HEAD | Integration decision |
|---|---|---|
|238|7df22d1c5cdc60bcf4e3414dacd35d23fdec7149|Existing base; retain hosted native fixes, never physical Apply|
|239|a4cbe48a649c376d1fddb022b7e43a5bfc2b3a3f|Port only release identity semantics and explanatory contract; add own runtime regressions|
|240|1fbe1710deab58b12ed6078ba7b38642d6070d8f|Readiness source unchanged; address review by moving secret validation before provider/connection|
|241|e96b7e8dde6c9927376f6311d6d08d52e705b144|Port byte bound and Unicode fail-closed; keep legacy fixed-port contract separate from G1|
|242|8093e292d53a0e1508d3531f006c9e967ac87062|Port ZIP budget/name checks and structural JUnit inspector with negative tests; retain existing API compatibility|
|244|79049906cb004e324bec5ef4cc53b85381cab83a|Input only, successor requires its own complete CI evidence|
|245|0892a1c850787d024a782ff3e44286c191529232|Two targeted fixes only; no whole-branch merge|

243 is an Issue. No source branches were modified. All later branch changes require
another exact-head comparison; no claim of permanent latest-head compatibility.

Credential fix: assert-based interpolation admission disappears with -O. The explicit
lowercase64-hex/type guard now precedes even provider attestation and connection,
not only CREATE ROLE. Full async context entry is executed in normal and optimized
child interpreters with forbidden provider/connection recorders and malformed type,
quote, surrogate, Unicode, empty, uppercase and oversized inputs. No real SQL in
these regression tests. Valid credentials still require the full Docker/cluster proof.

Network fix: exact str and <=65536 UTF-8 bytes before decoding; invalid Unicode is
rejected. Valid padded policy at65536 admitted,65537 rejected. The legacy validator's
hardcoded8765/55432 configuration is not the disposable G1 profile29441–29444;
never use its model PASS as host permission or reconfigure existing listeners.
Workers have no permitted PostgreSQL flow at any port.

Bootstrap fix: trusted source HEAD, active executable release SHA and observation
release are separate concepts. A different source/release pair is legal only with
matching policy/observation and matching release-specific mandatory file path.
Inventory hashes, exact file set, DLL/import/environment/custody/task checks stay
unchanged. Offline claims do not authenticate an installed current.version or grant
release switching rights. Tests reject path substitution and observation drift.

Acceptance fix: reject case-colliding/archive-alias members, encrypted/symlink
entries and total expansion above16MB; verify JUnit identities/counters/structural
text without claiming provenance. An inspector result always keeps lab_go=false.

Remaining P0 physical boundaries are in LS5_PC4_G1_AUTHORIZATION_REQUEST.md. Current
read-only LS5 observation is partial, PC4 not contacted, G1 executable controller
absent. No executable G1 manifest can honestly be marked ready. Generic owner
approval cannot repair those prerequisites. Execute/Cleanup remain unauthorized.

G0 producer/consumer regression discovered during actual authorized read-only
observation: SSH/Tailscale start_mode was emitted but not in the consumer/schema
allowlist. Added the exact bounded string field to both; unknown keys and wrong
types remain rejected. No collector changes, authorization promotion or host writes.
