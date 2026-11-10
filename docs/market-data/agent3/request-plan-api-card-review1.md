# Bybit request/subscription planning — API card review1

SOURCE-ONLY PROPOSAL. No implementation, imports, test/compile/discovery run,
provider/network/credentials or push. Root/A1/A2 API ACK REQUIRED before code.
Base Gridfb177d14b1e6e399bd9b66ae7cb35d3838acbd81,
tree2cba4b0a1ee7621ef213600d6334db8e9ac7dae1, source input only/not installable.

## Proposed NEW owned paths and signature

- Future implementation ONLY after ACK: grid/bybit_request_plan.py (NOT created).
- Prepared test SOURCE: tests/bybit_request_plan/test_request_plan.py.
- Exact frozen test inputs: tests/bybit_request_plan/fixtures/; directory-local
  .gitattributes preserves raw .json bytes, no repository-wide attributes changed.
- This card: docs/market-data/agent3/request-plan-api-card-review1.md.

prepare_bybit_request_plan(request_bytes: bytes, *, wire_contract_bytes: bytes,
provider_policy_bytes: bytes) -> PreparedBybitRequestPlan

PlanFormatError(ValueError): invalid/unsupported local data. One closed error
category, no partial plan or hidden fallback. No callback/provider/client/store/
clock/authority/credential argument. Function must not read files, sockets or time.
PreparedBybitRequestPlan: frozen/slotted immutable canonical_request_bytes and
canonical_plan_bytes; as_dict() returns detached parsed plan. No send/reserve/
consume/grant methods. A manually constructed plan is still data, never proof.

This LOCAL preparation ABI does NOT redefine166 acquire/consume/report wire or
an actual sender. No A1/A2 shared ABI or ledger mutation is introduced. No runtime
wiring of HTTP/WS/legacy retry, terminal403 or worker/coordinator is authorized.

## Frozen source/profile binding

wire_contract_bytes MUST be exact raw SHA256
16606dee585398ae6d92139ffc1cf2ed37a4d2e08759aaa08f0c3b85958b8049;
provider_policy_bytes exact raw SHA256
973f84f87de066d6686dfbe1177dc583637fa819aa21f988303e3a649abae3f1,
with immutable body digestb3ea69e77ef17b3cd2a894f16df32cb1caba3178efb8814800d4017507e15ca3.
Type=bytes and0<len<=65536 for EACH external profile BEFORE hashing/parsing.
Preflight type/length of ALL THREE byte arguments before ANY hash or decoding.
Raw hashes first after bounds; no canonicalizing a different image into admission.
Then validate policy/body/wire binding and exact six unique descriptors. Changed
enabled/validity/operation/priority/constraints, aliases or unknown profile deny.
Six enabled=false/null activation MUST remain unchanged; planning them is allowed
ONLY as DATA_ONLY_NOT_ADMITTED with send_permission=false. No active-policy variant.

operation_digest uses the existing policy operation_digest_fields projection,
not a new hashing rule: exchange,environment,regional_host_group,method,
path_or_ws_action,category,endpoint_class,credential_scope_reference (including
explicit null). It never hashes mutable limit/priority/enabled into scope identity.
Existing synthetic operation digests are test expectations, not send permission.

## Closed local request and canonical encoding

Top-level EXACT seven fields:
schema="grid.bybit.local-request-plan.v1-review1";
wire_profile_sha256; policy_raw_sha256; operation_id; requested_priority;
instruments; payload.

Request type=bytes,0<len<=32768, compact ASCII JSON, recursively ASCII-key sorted,
unique keys, no whitespace/BOM/trailing LF/optional escapes, no numeric literals,
float/bool coercion or unknown fields. Reject invalid/deep inputs before recursive
decode (maximum container depth8, nodes4096); arrays keep order. All request
counters/time/range/limit fields are canonical decimal strings and bounded u63;
time<=253402300799999. No implicit datetime or local time conversion.

Each instrument is exact exchange/category/symbol/instrument_version tuple of
frozen instrument schemab921dbae8dcc2231b571d11bc028ae7d04009234662760f8b72d5e3e70fdc5c7:
exchange=bybit, category=linear for these descriptors, uppercase symbol grammar
[A-Z0-9][A-Z0-9_-]{0,63}, version positive u63<=9223372036854775807. No normalization,
default version, lookup or allocator. Duplicate identities reject. Same symbol
with two versions/markets cannot be represented by an ambiguous topic mapping;
reject rather than silently collapse. Structural identity is NOT registry proof.

Absent market_ingestion_domain/checkpoint helpers on fb177 are NOT silently copied
or imported. Initial narrow tuple checks reproduce that existing schema's grammar
only, not another registry/engine. Root may instead admit the existing exact codec
closure BEFORE implementation; that packaging decision needs explicit ACK.

## Operation-specific exact payloads

| Frozen operation suffix | instruments | Closed payload / derived data |
|---|---|---|
| public.linear.instruments.v1 | [] | {limit:"1".."1000",cursor:null or printable opaque ASCII1..1024}; derive category=linear; preserve cursor exactly, no URL/path input |
| public.linear.kline.1m.v1 | exactly1 | {interval:"1",range:{start_ms,end_ms},limit:"1".."1000"}; aligned half-open range0<=start<end<=UTCmax, span<=1000minutes; derive start inclusive/end=end_ms-1, symbol/category from identity |
| public.linear.ws.connect.v1 | [] | {}; fixed host-group/path from descriptor, no socket/client/automatic ping configuration or resolved URL |
| public.linear.ws.ping.v1 | [] | {}; one local {op:"ping"} body, owned-slot requirement recorded UNVERIFIED, no clock request or heartbeat exemption |
| public.linear.ws.subscribe.v1 |1..100 unique identities | {topics:[...]}; strict complete requested topic set1..100, rules below |
| public.linear.ws.unsubscribe.v1 |1..100 unique identities | same topic rules; no actual unsubscribe, close or slot release |

requested_priority MUST belong to the EXACT selected descriptor. In particular
control/management promotion is not accepted; no remapping of current frozen
live_heartbeat/live_ingestion/live_recovery/historical_backfill vocabulary.

Topic subset for this first local planner: publicTrade.<SYMBOL>,
orderbook.50.<SYMBOL>, tickers.<SYMBOL>, matching actual source callsites only.
Each topic must map to an explicit instrument identity; each listed identity must
be used. Repeated topics reject, no silent dedup/sort. Unknown family/depth/category/
symbol/case/non-ASCII rejects. This is a deliberately narrow subset, no new provider
operation or claim that other real Bybit topics are invalid in general.

Stable input order is preserved; split20topics into EXACT10+10. Each planned
subscribe/unsubscribe body has<=10args and compact ASCII args image<=20000bytes.
Maximum100 requested topics=>maximum10 planned actions. Overflow rejects the WHOLE
plan, never truncate, drop, silently dedup or emit a first partial batch. Minimum
fresh attempts is one per resulting action, as DATA ONLY, no attempt IDs minted.

The100-topic limit bounds THIS COMPLETE REQUESTED PLAN, not an actual connection's
accumulated state. No existing-slot/current-subscription claim is accepted from
caller JSON. Actual sender must later validate live connection identity/current
union/count/slots through approved A1/A2 contract; this planner cannot enforce it.

## Closed prepared plan

schema="grid.bybit.data-only-plan.v1-review1"; state="DATA_ONLY_NOT_ADMITTED";
request_sha256; wire_profile_sha256; policy_raw_sha256; policy_body_digest;
operation_id; operation_digest; requested_priority; instrument_ids;
operation_enabled=false; activation_from_utc=null; activation_until_utc=null;
requires_owned_slot (descriptor bool); connection_state="UNVERIFIED";
minimum_fresh_attempts (positive decimal string); actions;
quota_reserved=false; consume_performed=false; send_permission=false.

Each action EXACT {method,host_group,path_or_action,query,body_ascii}:
HTTP uses fixedGET/host-group/path, string-valued query and null body;
WS_CONNECT fixed descriptor method/path, query=null/body=null;
WS_CONTROL fixed descriptor method/action, query=null/body_ascii=compact sorted
ASCII JSON {op,args} or {op:"ping"}. No actual hostname/IP/socket, private endpoint,
credential/header, grant/session/fence or scope expansion is generated.
Entire canonical_plan_bytes<=32768, measured before returning; excess rejects
whole output. Raw request bytes remain separately immutable, not serialized twice.
This local cap raises no existing mux/166 record limit or send allowance.

Unsupported /v5/market/time, time/bootstrap aliases, archive listing/download,
raw TCP readiness, private/order operations, arbitrary endpoints and unknown IDs
ALWAYS reject; no CLOCK/monitoring/high-priority bypass. A2 StrictOption1, logical
DISABLED and current provider/data/egress/storage gates remain untouched.

## Test source and next gate

Tests import ONLY the actual FUTURE module, never a copied planner/mock fallback.
They are NOT imported, compiled, discovered or executed now; no RED/PASS claimed.
Frozen input files are copied byte-identical, not activated or rewritten.
Source expectations cover six descriptor digests/data-only status, exact identity,
caller flags, hashes, bounds, stable20->10+10, duplicate/malformed/unsupported
requests and no partial output. Planned IO/clock guards apply during future calls.

Root routes exact card/test/fixture bytes to A1/A2. After exact API/allocation ACK,
next action is ONE explicit missing-module RED run, preserve log, then owned pure
implementation and meaningful negative tests. No WS/HTTP/legacy consumer wiring
until separate contract/source ACK. No provider tests/credentials/push/runtime now.
Source-only local commit may pin review artifacts; not a shared schema freeze,
implementation approval, hosted/physical acceptance or operation permission.
