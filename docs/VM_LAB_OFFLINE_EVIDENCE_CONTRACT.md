# VM Lab offline hardening and evidence draft — contract v1

Base: PR198 `9a2d77c2f1e89c5a2e7d35a876e887dc6ca488d3`.
This change hardens the PlanOnly contract; it does not provision, inspect, start,
connect to, alter or clean any VM, computer, disk, network, credential, PostgreSQL,
service, installed Grid resource or production system. Schema2 remains disabled.
Existing native ABA and global kernel exhaustion blockers remain unresolved.

## Reproduced findings and scope

- P2 policy consistency: aliases `-`, `.`, `_`, numeric addresses and conservative
  protected-node variants `LS005`, `ls-0007.lab`, `ls__05` previously passed. Strict
  bounded ASCII labels now reject ambiguous syntax/numeric addresses; case,
  hyphen/underscore and zero-padded protected LS5/LS7 variants are blocked.
- P2 API error consistency: unescaped surrogate strings and oversized integer JSON
  raised ValueError subclasses/messages outside the fixed-code API contract.
  CLI already sanitized them, but direct callers did not receive stable codes.
  Both entry points now use a bounded JSON-only loader/value guard and fixed codes.
- Compatibility defect: ordinary protected paths with spaces and lowercase drives
  were rejected. Supported unambiguous ASCII Windows paths now compare case
  insensitively, with drive roots and both ancestor/descendant overlap directions.
  No existing lexical overlap bypass was demonstrated by the tests; do not claim one.

The bounded mutation sweep did NOT establish an existing uncaught TypeError,
AttributeError or KeyError for JSON-valid type substitutions. Exact schema checks
already contained many cases. New bounded type validation makes the accepted
input domain explicit and adds regression coverage rather than claiming an
unreproduced exception defect was fixed.

## Parser and direct API exception contract

`vm_lab_json.load` limits input to65536 characters AND65536 UTF-8 bytes before
parsing. A quote/escape-aware scan rejects nesting beyond24 before the recursive
stdlib parser. Iterative value validation rejects depth>24, >4096 nodes,
containers>256 entries, aggregate string characters>65536, non-JSON Python types,
non-string dictionary keys, surrogates, nonfinite floats and integers>256 bits.
JSON integer text>80 characters is refused before conversion; duplicate keys at
any depth and nonfinite constants are rejected. Valid non-BMP text is processed
safely, but policy fields remain restricted to their documented ASCII syntax.
Direct cyclic objects terminate at the same depth/node budget. No global Python
recursion/integer settings are changed.

For invalid supported input, public validators raise ValueError with a fixed bounded
`VM_[A-Z_]+` code. CLI returns exit2 and sanitized BLOCKED JSON, never raw input,
credentials or a traceback for validation failures. Valid metadata returns exit0
with BLOCKED and false readiness/authorization. OS failure delivering stdin/stdout,
interpreter termination or physical resource failure is not promised to produce a
JSON report; no operation is authorized even if reporting fails. Memory/time
bounds apply to this input-processing design, not production HA or host attestation.

Mutation tests replace every nested plan field with bool/int/float/string/list/dict/
null, huge numbers and non-BMP text; test top-level non-objects, excessive nesting,
surrogates, malformed/duplicate/nonfinite JSON, cycles and realistic path aliases.
A successful mutation can only yield blocked metadata; every refusal must be a
fixed-code ValueError. No native API, machine lookup, service or VM is used.

## Conservative path and computer-name semantics

Syntax is checked BEFORE PureWindowsPath construction. Reject UNC/device/extended
paths, forward slashes, ADS, 8.3 tildes, empty/repeated separators, dot/dotdot,
leading/trailing segment spaces, trailing dots, reserved DOS names, control chars,
unapproved punctuation and non-ASCII lookalikes. Canonical drive roots can appear
in protected inventory to block an entire drive. Internal spaces in protected
segments are supported. Planned root remains exactly `X:\GridVmLab\<lab_id>`
modulo Windows case equivalence. Parent/child comparisons are conservative lexical
checks; siblings with only a textual prefix are not mistaken for descendants.

Drive letters/volume identities, mount points, reparse ancestors, short-name aliases,
actual installed resources and storage ownership remain UNPROVEN. Different drive
letters can name the same storage. The code never calls resolve/stat/host APIs, so
passing lexical checks cannot attest physical separation. Ambiguous syntax is
blocked instead of normalized into a possibly safe path.

Host IDs remain fresh UUID declarations, NOT actual computer identity. Aliases
must be nonempty valid bounded ASCII labels, with no empty DNS components or
numeric-only address spelling; duplicate case aliases are refused. Protected LS5/7
normalization is conservative and intentionally may reject an unrelated zero-padded
name. An operator can still lie or omit aliases: `inventory_complete=true` is NEVER
proof. Report includes inventory_assurance=DECLARED_ONLY and explicit
HOST_ALIAS_INVENTORY_NOT_ATTESTED blocker. No DNS, SSH or Tailscale discovery occurs.

## Offline future-observer draft contract

`vm_lab_evidence.draft(plan, observer_id)` constructs only schema1
VmLabIsolationEvidenceDraft. `inspect_evidence(raw,plan)` accepts strict bounded
JSON and checks:

- plan_sha256 of the validated plan;
- payload_sha256 of the payload;
- exact nested schemas and types, observer GUID declaration, bound lab/VM/host IDs,
  image SHA256 and quotas;
- identity_evidence=NOT_COLLECTED, isolation_evidence=NOT_COLLECTED,
  approval_evidence=NOT_AUTHENTICATED, observer authority=UNAUTHENTICATED_DECLARATION;
- exact ordered twelve-case catalogue from the PlanOnly specification; every case
  execution=NOT_RUN and assurance=BLOCKED_UNPROVEN. Missing/duplicate/extra/PASS/
  SKIPPED cases and supplied signatures or approval/token assertions are refused.

Canonicalization v1: validate bounded JSON-only values; json.dumps with sorted keys,
compact separators, ensure_ascii=true and allow_nan=false, then ASCII bytes and
SHA256. Whitespace/key order outside this canonical representation has no effect.
Array order and exact JSON types are significant (true cannot impersonate integer1).
Plan binding covers declarations, including quotas and approval metadata; it does
not independently authenticate any of them. Drafts have no timestamps, certificate,
key store, signature verification, trust policy, real observer protocol or network.
No genuine executed evidence can be admitted by this draft-only schema.

**SHA256 detects inconsistency, not forgery.** Any actor can recompute hashes of
fabricated declarations. Hash agreement returns integrity=MATCH_METADATA_ONLY,
authentication=UNVERIFIED, status=BLOCKED, verified_safety_cases0,
readiness_passed=false, execution_authorized=false and physical_ready=false.
All twelve guest cases remain NOT_RUN. A future authenticated attestation pipeline
requires a separately reviewed versioned schema, trusted observer/key/approval
boundary, freshness/replay rules and actual different-token guest evidence. None
is implied or implemented here. Previous hosted native GUID tests are not such proof.

## Verification, safety audit and remaining stops

Python3.11/3.12 run mutation and evidence-forgery regressions alongside existing
PlanOnly tests; PS5.1/7 validate both plan and draft output using only a checked-in
synthetic fixture. No multiline JSON normalization or physical target is involved.
Existing native/packaging/RuntimeGuard/LegacyRollback gates remain intact.

STOP on hostile host administrator, unverified host/image/approval/token identity,
unknown storage/alias/network state, unexpected case or status, failed integrity,
resource uncertainty, ABA or kernel-exhaustion uncertainty. Metadata and green CI
cannot remove these stops or grant independent approval. Preserve-only lifecycle
and no executor remain unchanged; no cleanup/poweroff/disposal is authorized.
Rollback for this PR is reviewed source revert only; no physical state changed.
