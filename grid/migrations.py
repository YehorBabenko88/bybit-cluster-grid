import logging
log=logging.getLogger("migrations")

MIGRATIONS=[
(1,"baseline_jsonb_extensible",[
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS extra jsonb NOT NULL DEFAULT '{}'::jsonb",
"ALTER TABLE footprint_1m ADD COLUMN IF NOT EXISTS extra jsonb NOT NULL DEFAULT '{}'::jsonb",
]),
(2,"market_microstructure_tables",[
"""CREATE TABLE IF NOT EXISTS orderbook_snapshots(
symbol text NOT NULL, ts timestamptz NOT NULL, best_bid numeric, best_ask numeric, spread numeric,
bid_depth numeric, ask_depth numeric, imbalance numeric, walls jsonb NOT NULL DEFAULT '[]'::jsonb,
book jsonb NOT NULL DEFAULT '{}'::jsonb, extra jsonb NOT NULL DEFAULT '{}'::jsonb, PRIMARY KEY(symbol,ts))""",
"""CREATE TABLE IF NOT EXISTS derivatives_metrics(
symbol text NOT NULL, ts timestamptz NOT NULL, open_interest numeric, funding_rate numeric,
mark_price numeric, index_price numeric, basis numeric, extra jsonb NOT NULL DEFAULT '{}'::jsonb,
PRIMARY KEY(symbol,ts))"""
]),
(3,"minute_data_quality",[
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS quality_status text NOT NULL DEFAULT 'UNKNOWN'",
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS quality_reasons jsonb NOT NULL DEFAULT '[]'::jsonb",
"CREATE INDEX IF NOT EXISTS candles_1m_quality_idx ON candles_1m(quality_status,ts DESC)"
]),
(4,"market_features_1m",[
"""CREATE TABLE IF NOT EXISTS market_features_1m(
symbol text NOT NULL, ts timestamptz NOT NULL, eligible boolean NOT NULL,
quality_status text NOT NULL, features jsonb NOT NULL, capabilities jsonb NOT NULL,
built_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(symbol,ts))""",
"CREATE INDEX IF NOT EXISTS market_features_1m_eligible_idx ON market_features_1m(eligible,ts DESC)"
]),
(5,"volatility_regime_columns",[
"ALTER TABLE market_features_1m ADD COLUMN IF NOT EXISTS regime text NOT NULL DEFAULT 'QUIET'",
"ALTER TABLE market_features_1m ADD COLUMN IF NOT EXISTS regime_score double precision NOT NULL DEFAULT 1.0",
"CREATE INDEX IF NOT EXISTS market_features_1m_regime_idx ON market_features_1m(regime,ts DESC)"
]),
(6,"poc_lifecycle",[
"""CREATE TABLE IF NOT EXISTS poc_lifecycle(
symbol text NOT NULL, source_ts timestamptz NOT NULL, poc_price numeric NOT NULL,
source_close numeric, source_regime text, source_features jsonb NOT NULL DEFAULT '{}'::jsonb,
status text NOT NULL DEFAULT 'NAKED', first_touch_ts timestamptz, first_touch_minutes integer,
first_touch_kind text, cross_ts timestamptz, acceptance_ts timestamptz,
touch_count integer NOT NULL DEFAULT 0, max_distance_pct double precision NOT NULL DEFAULT 0,
last_checked_ts timestamptz, PRIMARY KEY(symbol,source_ts))""",
"CREATE INDEX IF NOT EXISTS poc_lifecycle_open_idx ON poc_lifecycle(symbol,status,source_ts)"
]),
(7,"historical_level_events",[
"""CREATE TABLE IF NOT EXISTS historical_levels(
symbol text NOT NULL, timeframe text NOT NULL, level_kind text NOT NULL,
source_ts timestamptz NOT NULL, price numeric NOT NULL, active boolean NOT NULL DEFAULT true,
first_cross_ts timestamptz, test_count integer NOT NULL DEFAULT 0,
PRIMARY KEY(symbol,timeframe,level_kind,source_ts))""",
"""CREATE TABLE IF NOT EXISTS level_events(
id bigserial PRIMARY KEY, symbol text NOT NULL, timeframe text NOT NULL, level_kind text NOT NULL,
source_ts timestamptz NOT NULL, level_price numeric NOT NULL, event_ts timestamptz NOT NULL,
event_type text NOT NULL, direction text, pre_features jsonb NOT NULL DEFAULT '{}'::jsonb,
event_features jsonb NOT NULL DEFAULT '{}'::jsonb, outcome jsonb NOT NULL DEFAULT '{}'::jsonb)""",
"CREATE INDEX IF NOT EXISTS level_events_lookup_idx ON level_events(symbol,timeframe,event_type,event_ts DESC)"
]),
(8,"historical_level_availability",[
"ALTER TABLE historical_levels ADD COLUMN IF NOT EXISTS available_ts timestamptz",
"CREATE INDEX IF NOT EXISTS historical_levels_active_idx ON historical_levels(symbol,active,timeframe,price)"
]),
(9,"level_event_idempotency",[
"CREATE UNIQUE INDEX IF NOT EXISTS level_events_unique_event_idx ON level_events(symbol,timeframe,level_kind,source_ts,event_ts,event_type)"
]),
(10,"observer_recovery_state",[
"""CREATE TABLE IF NOT EXISTS observer_checkpoints(
observer text NOT NULL, symbol text NOT NULL, last_ts timestamptz,
state jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(observer,symbol))""",
"ALTER TABLE level_events ADD COLUMN IF NOT EXISTS quality_status text NOT NULL DEFAULT 'UNKNOWN'",
"ALTER TABLE level_events ADD COLUMN IF NOT EXISTS completeness double precision NOT NULL DEFAULT 0",
"ALTER TABLE level_events ADD COLUMN IF NOT EXISTS ml_eligible boolean NOT NULL DEFAULT false"
]),
(11,"ml_event_samples",[
"""CREATE TABLE IF NOT EXISTS ml_event_samples(
sample_id bigserial PRIMARY KEY, symbol text NOT NULL, event_id bigint REFERENCES level_events(id),
sample_type text NOT NULL, feature_ts timestamptz NOT NULL, event_ts timestamptz NOT NULL,
features jsonb NOT NULL, instrument_features jsonb NOT NULL DEFAULT '{}'::jsonb,
target jsonb NOT NULL DEFAULT '{}'::jsonb, target_ready boolean NOT NULL DEFAULT false,
quality_status text NOT NULL, split_group text, created_at timestamptz NOT NULL DEFAULT now())""",
"CREATE UNIQUE INDEX IF NOT EXISTS ml_event_samples_event_type_idx ON ml_event_samples(event_id,sample_type)",
"CREATE INDEX IF NOT EXISTS ml_event_samples_train_idx ON ml_event_samples(target_ready,quality_status,event_ts)"
]),
(12,"ml_orchestrator_concurrency",[
"""CREATE TABLE IF NOT EXISTS ml_jobs(
id uuid PRIMARY KEY, job_type text NOT NULL, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
status text NOT NULL DEFAULT 'queued', priority integer NOT NULL DEFAULT 100,
lease_owner text, lease_until timestamptz, attempts integer NOT NULL DEFAULT 0,
dataset_cutoff timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
started_at timestamptz, finished_at timestamptz, error text)""",
"CREATE INDEX IF NOT EXISTS ml_jobs_claim_idx ON ml_jobs(status,priority,created_at)",
"""CREATE TABLE IF NOT EXISTS dataset_snapshots(
id uuid PRIMARY KEY, purpose text NOT NULL, cutoff_ts timestamptz NOT NULL,
created_at timestamptz NOT NULL DEFAULT now(), created_by text NOT NULL,
criteria jsonb NOT NULL DEFAULT '{}'::jsonb, status text NOT NULL DEFAULT 'ready')""",
"""CREATE TABLE IF NOT EXISTS service_leases(
service_key text PRIMARY KEY, owner text NOT NULL, lease_until timestamptz NOT NULL,
heartbeat_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb)"""
]),
(13,"ml_artifact_lifecycle",[
"""CREATE TABLE IF NOT EXISTS ml_artifacts(
id uuid PRIMARY KEY, artifact_type text NOT NULL, owner_job uuid,
storage_uri text NOT NULL, bytes bigint NOT NULL DEFAULT 0,
status text NOT NULL DEFAULT 'ACTIVE', reusable boolean NOT NULL DEFAULT false,
expires_at timestamptz, last_used_at timestamptz NOT NULL DEFAULT now(),
created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb)""",
"CREATE INDEX IF NOT EXISTS ml_artifacts_gc_idx ON ml_artifacts(status,reusable,expires_at,last_used_at)"
]),
(14,"ml_lifecycle_registry",[
"ALTER TABLE dataset_snapshots ADD COLUMN IF NOT EXISTS dataset_hash text",
"ALTER TABLE dataset_snapshots ADD COLUMN IF NOT EXISTS sample_count bigint NOT NULL DEFAULT 0",
"ALTER TABLE dataset_snapshots ADD COLUMN IF NOT EXISTS feature_version text",
"""CREATE TABLE IF NOT EXISTS model_registry(
id uuid PRIMARY KEY, model_family text NOT NULL, symbol_scope jsonb NOT NULL DEFAULT '[]'::jsonb,
dataset_id uuid NOT NULL REFERENCES dataset_snapshots(id), parent_model_id uuid,
status text NOT NULL DEFAULT 'CANDIDATE', artifact_id uuid,
code_version text, feature_version text, hyperparameters jsonb NOT NULL DEFAULT '{}'::jsonb,
created_at timestamptz NOT NULL DEFAULT now(), promoted_at timestamptz)""",
"""CREATE TABLE IF NOT EXISTS model_evaluations(
id uuid PRIMARY KEY, model_id uuid NOT NULL REFERENCES model_registry(id),
stage text NOT NULL, dataset_id uuid REFERENCES dataset_snapshots(id),
metrics jsonb NOT NULL, passed boolean NOT NULL, evaluator_version text,
created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(model_id,stage,dataset_id))""",
"""CREATE TABLE IF NOT EXISTS shadow_predictions(
model_id uuid NOT NULL REFERENCES model_registry(id), symbol text NOT NULL,
event_ts timestamptz NOT NULL, setup_type text NOT NULL, prediction jsonb NOT NULL,
outcome jsonb, evaluated_at timestamptz, PRIMARY KEY(model_id,symbol,event_ts,setup_type))"""
]),
(15,"immutable_dataset_membership",[
"""CREATE TABLE IF NOT EXISTS dataset_samples(
dataset_id uuid NOT NULL REFERENCES dataset_snapshots(id) ON DELETE CASCADE,
sample_id bigint NOT NULL REFERENCES ml_event_samples(sample_id),
ordinal bigint NOT NULL, PRIMARY KEY(dataset_id,sample_id), UNIQUE(dataset_id,ordinal))"""
]),
(16,"consumer_safe_retention_and_control_state",[
"""CREATE TABLE IF NOT EXISTS consumer_watermarks(
dataset text NOT NULL, consumer text NOT NULL, symbol text NOT NULL,
consumed_through timestamptz NOT NULL, required boolean NOT NULL DEFAULT true,
updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(dataset,consumer,symbol))""",
"""CREATE TABLE IF NOT EXISTS retention_holds(
id uuid PRIMARY KEY, dataset text NOT NULL, symbol text, from_ts timestamptz,
through_ts timestamptz, reason text NOT NULL, owner_type text NOT NULL,
owner_id text NOT NULL, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())""",
"CREATE INDEX IF NOT EXISTS retention_holds_lookup_idx ON retention_holds(dataset,symbol,from_ts,through_ts)",
"""CREATE TABLE IF NOT EXISTS replicated_control_state(
state_key text PRIMARY KEY, value jsonb NOT NULL, version bigint NOT NULL DEFAULT 1,
updated_at timestamptz NOT NULL DEFAULT now(), updated_by text NOT NULL)"""
]),
(17,"integrity_repair_state",[
"""CREATE TABLE IF NOT EXISTS integrity_repairs(
id uuid PRIMARY KEY,node_id text NOT NULL,target_version text NOT NULL,
status text NOT NULL DEFAULT 'queued',required_health_acks integer NOT NULL DEFAULT 3,
health_acks integer NOT NULL DEFAULT 0,previous_version text,
files jsonb NOT NULL DEFAULT '[]'::jsonb,created_at timestamptz NOT NULL DEFAULT now(),
deadline timestamptz NOT NULL DEFAULT now()+interval '10 minutes',last_error text)""",
"CREATE INDEX IF NOT EXISTS integrity_repairs_node_status_idx ON integrity_repairs(node_id,status,created_at DESC)"
]),
(18,"ml_fencing_immutable_payloads_and_label_horizon",[
"ALTER TABLE ml_jobs ADD COLUMN IF NOT EXISTS lease_generation bigint NOT NULL DEFAULT 0",
"ALTER TABLE ml_jobs ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 5",
"ALTER TABLE ml_jobs ADD COLUMN IF NOT EXISTS not_before timestamptz",
"ALTER TABLE ml_event_samples ADD COLUMN IF NOT EXISTS label_end_ts timestamptz",
"""CREATE TABLE IF NOT EXISTS dataset_sample_payloads(
dataset_id uuid NOT NULL REFERENCES dataset_snapshots(id) ON DELETE CASCADE,
sample_id bigint NOT NULL,ordinal bigint NOT NULL,payload jsonb NOT NULL,
payload_hash text NOT NULL,event_ts timestamptz NOT NULL,feature_ts timestamptz NOT NULL,
label_end_ts timestamptz,split_group text,
PRIMARY KEY(dataset_id,sample_id),UNIQUE(dataset_id,ordinal))""",
"CREATE INDEX IF NOT EXISTS dataset_payload_event_idx ON dataset_sample_payloads(dataset_id,event_ts,ordinal)"
]),
(19,"ml_job_deduplication",[
"ALTER TABLE ml_jobs ADD COLUMN IF NOT EXISTS dedupe_key text",
"""CREATE UNIQUE INDEX IF NOT EXISTS ml_jobs_active_dedupe_idx ON ml_jobs(dedupe_key)
WHERE dedupe_key IS NOT NULL AND status IN ('queued','assigned','running')"""
]),
(20,"ml_resource_reservations",[
"""CREATE TABLE IF NOT EXISTS ml_resource_reservations(
job_id uuid PRIMARY KEY REFERENCES ml_jobs(id) ON DELETE CASCADE,
node_id text NOT NULL,cpu double precision NOT NULL,ram_gb double precision NOT NULL,
scratch_gb double precision NOT NULL,gpu boolean NOT NULL DEFAULT false,
lease_generation bigint NOT NULL DEFAULT 0,expires_at timestamptz NOT NULL,
created_at timestamptz NOT NULL DEFAULT now())""",
"CREATE INDEX IF NOT EXISTS ml_reservations_node_idx ON ml_resource_reservations(node_id,expires_at)"
]),
(21,"markov_transition_edge_results",[
"""CREATE TABLE IF NOT EXISTS markov_transition_edges(
dataset_id uuid REFERENCES dataset_snapshots(id),model_id uuid REFERENCES model_registry(id),
strategy_name text NOT NULL,symbol text NOT NULL DEFAULT '*',setup_type text NOT NULL,
state_from text NOT NULL,state_to text NOT NULL,trades bigint NOT NULL,net_pnl double precision NOT NULL,
expectancy double precision NOT NULL,hit_rate double precision NOT NULL,
created_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(dataset_id,model_id,strategy_name,symbol,setup_type,state_from,state_to))"""
]),
(22,"strategy_comparison_results",[
"""CREATE TABLE IF NOT EXISTS strategy_comparison_results(
dataset_id uuid REFERENCES dataset_snapshots(id),strategy_name text NOT NULL,variant text NOT NULL,
comparison_group text NOT NULL,metrics jsonb NOT NULL,incremental jsonb,uncertainty jsonb,
created_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(dataset_id,strategy_name,variant,comparison_group))"""
]),
(23,"historical_experiment_runs",[
"""CREATE TABLE IF NOT EXISTS historical_experiment_runs(
id uuid PRIMARY KEY,dataset_id uuid NOT NULL REFERENCES dataset_snapshots(id),
strategy_name text NOT NULL,status text NOT NULL DEFAULT 'queued',
config jsonb NOT NULL DEFAULT '{}'::jsonb,total_symbols integer NOT NULL DEFAULT 0,
completed_symbols integer NOT NULL DEFAULT 0,failed_symbols integer NOT NULL DEFAULT 0,
created_at timestamptz NOT NULL DEFAULT now(),started_at timestamptz,finished_at timestamptz,
last_error text)""",
"""CREATE TABLE IF NOT EXISTS historical_experiment_checkpoints(
run_id uuid NOT NULL REFERENCES historical_experiment_runs(id) ON DELETE CASCADE,
symbol text NOT NULL,status text NOT NULL DEFAULT 'queued',attempts integer NOT NULL DEFAULT 0,
started_at timestamptz,finished_at timestamptz,last_error text,
PRIMARY KEY(run_id,symbol))""",
"CREATE INDEX IF NOT EXISTS historical_experiment_cp_status_idx ON historical_experiment_checkpoints(run_id,status,symbol)"
]),
(24,"cold_start_backfill",[
"""CREATE TABLE IF NOT EXISTS ohlcv_1m(
symbol text NOT NULL,ts timestamptz NOT NULL,open numeric NOT NULL,high numeric NOT NULL,
low numeric NOT NULL,close numeric NOT NULL,volume numeric NOT NULL,turnover numeric,
source text NOT NULL DEFAULT 'BYBIT_REST',PRIMARY KEY(symbol,ts))""",
"CREATE INDEX IF NOT EXISTS ohlcv_1m_symbol_ts_idx ON ohlcv_1m(symbol,ts DESC)",
"""CREATE TABLE IF NOT EXISTS market_backfill_state(
symbol text NOT NULL,timeframe text NOT NULL DEFAULT '1',status text NOT NULL DEFAULT 'queued',
oldest_loaded_ts timestamptz,newest_loaded_ts timestamptz,next_end_ms bigint,
attempts integer NOT NULL DEFAULT 0,last_error text,updated_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(symbol,timeframe))""",
"CREATE INDEX IF NOT EXISTS market_backfill_status_idx ON market_backfill_state(status,updated_at)"
]),
(25,"market_data_capabilities",[
"""CREATE TABLE IF NOT EXISTS market_data_capabilities(
symbol text PRIMARY KEY,ohlcv_history text NOT NULL DEFAULT 'UNKNOWN',
trade_history text NOT NULL DEFAULT 'UNKNOWN',live_trades text NOT NULL DEFAULT 'UNKNOWN',
live_orderbook text NOT NULL DEFAULT 'UNKNOWN',footprint_history text NOT NULL DEFAULT 'UNKNOWN',
orderbook_history text NOT NULL DEFAULT 'UNAVAILABLE',
trade_history_from timestamptz,trade_history_through timestamptz,
updated_at timestamptz NOT NULL DEFAULT now(),details jsonb NOT NULL DEFAULT '{}'::jsonb)""",
"""CREATE TABLE IF NOT EXISTS trade_archive_backfill(
symbol text NOT NULL,archive_date date NOT NULL,status text NOT NULL DEFAULT 'queued',
source_uri text,bytes bigint,rows bigint,sha256 text,attempts integer NOT NULL DEFAULT 0,
last_error text,updated_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(symbol,archive_date))""",
"CREATE INDEX IF NOT EXISTS trade_archive_backfill_status_idx ON trade_archive_backfill(status,archive_date,symbol)"
]),
(26,"archive_compaction_manifests",[
"""CREATE TABLE IF NOT EXISTS archive_compaction_manifests(
symbol text NOT NULL,archive_date date NOT NULL,source_sha256 text NOT NULL,
source_rows bigint NOT NULL,derived_candles bigint NOT NULL,derived_footprint_rows bigint NOT NULL,
min_ts timestamptz,max_ts timestamptz,status text NOT NULL DEFAULT 'DERIVED',
verified_at timestamptz,raw_deleted_at timestamptz,details jsonb NOT NULL DEFAULT '{}'::jsonb,
PRIMARY KEY(symbol,archive_date))""",
"CREATE INDEX IF NOT EXISTS archive_compaction_status_idx ON archive_compaction_manifests(status,archive_date)"
]),
(27,"trade_archive_discovery",[
"""CREATE TABLE IF NOT EXISTS trade_archive_discovery(
symbol text PRIMARY KEY,status text NOT NULL DEFAULT 'queued',mode text,
earliest_date date,latest_date date,discovered_files integer NOT NULL DEFAULT 0,
last_scan_at timestamptz,last_error text,details jsonb NOT NULL DEFAULT '{}'::jsonb)""",
"CREATE INDEX IF NOT EXISTS trade_archive_discovery_status_idx ON trade_archive_discovery(status,last_scan_at)"
]),
(28,"legacy_bootstrap_import",[
"""CREATE TABLE IF NOT EXISTS legacy_bootstrap_imports(
source_id text PRIMARY KEY,source_path text NOT NULL,research_path text,
research_cutoff timestamptz,status text NOT NULL DEFAULT 'PENDING',
coverage_symbols integer NOT NULL DEFAULT 0,imported_candles bigint NOT NULL DEFAULT 0,
imported_levels bigint NOT NULL DEFAULT 0,imported_samples bigint NOT NULL DEFAULT 0,
manifest jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now(),
verified_at timestamptz,last_error text)""",
"""CREATE TABLE IF NOT EXISTS legacy_symbol_coverage(
source_id text NOT NULL REFERENCES legacy_bootstrap_imports(source_id) ON DELETE CASCADE,
symbol text NOT NULL,min_ts timestamptz,max_ts timestamptz,candles bigint NOT NULL,
gap_minutes bigint NOT NULL DEFAULT 0,coverage_fingerprint text NOT NULL,
PRIMARY KEY(source_id,symbol))""",
"""CREATE TABLE IF NOT EXISTS imported_historical_levels(
source_id text NOT NULL REFERENCES legacy_bootstrap_imports(source_id) ON DELETE CASCADE,
symbol text NOT NULL,timeframe text NOT NULL,level_type text NOT NULL,source_start timestamptz NOT NULL,
available_at timestamptz NOT NULL,price numeric NOT NULL,trigger numeric NOT NULL,
broken boolean NOT NULL,broken_at timestamptz,entries integer NOT NULL DEFAULT 0,
PRIMARY KEY(source_id,symbol,timeframe,level_type,source_start,price))""",
"""CREATE TABLE IF NOT EXISTS legacy_research_samples(
source_id text NOT NULL REFERENCES legacy_bootstrap_imports(source_id) ON DELETE CASCADE,
symbol text NOT NULL,sample_key text NOT NULL,sample_type text NOT NULL,event_ts timestamptz NOT NULL,
split text,payload jsonb NOT NULL,PRIMARY KEY(source_id,symbol,sample_key))""",
"CREATE INDEX IF NOT EXISTS legacy_research_samples_type_idx ON legacy_research_samples(sample_type,event_ts)"
]),
(29,"legacy_symbol_import_state",[
"ALTER TABLE legacy_symbol_coverage ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'PENDING'",
"ALTER TABLE legacy_symbol_coverage ADD COLUMN IF NOT EXISTS imported_candles bigint NOT NULL DEFAULT 0",
"ALTER TABLE legacy_symbol_coverage ADD COLUMN IF NOT EXISTS verified_at timestamptz",
"ALTER TABLE legacy_symbol_coverage ADD COLUMN IF NOT EXISTS last_error text"
]),
(30,"required_retention_consumer_registry",[
"""CREATE TABLE IF NOT EXISTS retention_consumers(
dataset text NOT NULL,consumer text NOT NULL,required boolean NOT NULL DEFAULT true,
active boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT now(),
updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(dataset,consumer))"""
]),
(31,"derived_minute_completion",[
"""CREATE TABLE IF NOT EXISTS derived_minute_state(
symbol text NOT NULL,ts timestamptz NOT NULL,status text NOT NULL DEFAULT 'DONE',
processed_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(symbol,ts))""",
"CREATE INDEX IF NOT EXISTS derived_minute_state_ts_idx ON derived_minute_state(ts)"
]),
(32,"pilot_bootstrap_state",[
"""CREATE TABLE IF NOT EXISTS pilot_bootstrap_state(
node_id text PRIMARY KEY,mode text NOT NULL DEFAULT 'PILOT_BOOTSTRAP',
phase text NOT NULL DEFAULT 'WAITING',paused boolean NOT NULL DEFAULT false,
progress numeric NOT NULL DEFAULT 0,source_path text,research_path text,
details jsonb NOT NULL DEFAULT '{}'::jsonb,updated_at timestamptz NOT NULL DEFAULT now(),
completed_at timestamptz,expansion_notified_at timestamptz)""",
"CREATE INDEX IF NOT EXISTS pilot_bootstrap_mode_idx ON pilot_bootstrap_state(mode,phase)"
]),
(33,"telegram_update_idempotency",[
"""CREATE TABLE IF NOT EXISTS telegram_updates(
update_id bigint PRIMARY KEY,chat_id text,command text,status text NOT NULL DEFAULT 'CLAIMED',
claimed_by text NOT NULL,claimed_at timestamptz NOT NULL DEFAULT now(),
completed_at timestamptz,error text)"""
]),
(34,"microstructure_research_capture",[
"""CREATE TABLE IF NOT EXISTS setup_candidates(
id bigserial PRIMARY KEY,symbol text NOT NULL,setup_type text NOT NULL,
direction text NOT NULL,detected_at timestamptz NOT NULL,reference_price numeric,
confidence double precision,features jsonb NOT NULL DEFAULT '{}'::jsonb,
state text NOT NULL DEFAULT 'DETECTED',invalidated_at timestamptz,
outcome jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now())""",
"CREATE INDEX IF NOT EXISTS setup_candidates_lookup_idx ON setup_candidates(setup_type,symbol,detected_at DESC)",
"CREATE INDEX IF NOT EXISTS setup_candidates_state_idx ON setup_candidates(state,detected_at DESC)"
]),
(35,"ml_microstructure_storage",[
"""CREATE TABLE IF NOT EXISTS microstructure_raw_events(
id bigserial PRIMARY KEY,symbol text NOT NULL,event_ts timestamptz NOT NULL,
event_type text NOT NULL,payload jsonb NOT NULL,ingest_ts timestamptz NOT NULL DEFAULT now())""",
"CREATE INDEX IF NOT EXISTS microstructure_raw_symbol_ts_idx ON microstructure_raw_events(symbol,event_ts DESC)",
"CREATE INDEX IF NOT EXISTS microstructure_raw_type_ts_idx ON microstructure_raw_events(event_type,event_ts DESC)",
"CREATE UNIQUE INDEX IF NOT EXISTS microstructure_raw_dedupe_idx ON microstructure_raw_events(symbol,event_ts,event_type,md5(payload::text))",
"""CREATE TABLE IF NOT EXISTS microstructure_samples(
symbol text NOT NULL,ts timestamptz NOT NULL,known_at timestamptz NOT NULL,
payload jsonb NOT NULL,ingest_ts timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY(symbol,ts))""",
"CREATE INDEX IF NOT EXISTS microstructure_samples_known_idx ON microstructure_samples(symbol,known_at DESC)"
]),
(36,"continuous_microstructure_ml_samples",[
"""CREATE TABLE IF NOT EXISTS microstructure_ml_samples(
id bigserial PRIMARY KEY,symbol text NOT NULL,feature_ts timestamptz NOT NULL,
known_at timestamptz NOT NULL,horizon_seconds integer NOT NULL,
features jsonb NOT NULL,target jsonb NOT NULL DEFAULT '{}'::jsonb,
target_ready boolean NOT NULL DEFAULT false,label_end_ts timestamptz,
quality_status text NOT NULL DEFAULT 'GOOD',created_at timestamptz NOT NULL DEFAULT now(),
UNIQUE(symbol,feature_ts,horizon_seconds))""",
"CREATE INDEX IF NOT EXISTS microstructure_ml_ready_idx ON microstructure_ml_samples(target_ready,quality_status,feature_ts)",
"CREATE INDEX IF NOT EXISTS microstructure_ml_pending_idx ON microstructure_ml_samples(symbol,target_ready,label_end_ts)"
]),
(37,"distributed_research_bridge",[
"""CREATE TABLE IF NOT EXISTS research_runs(
id uuid PRIMARY KEY,kind text NOT NULL,dataset_id uuid REFERENCES dataset_snapshots(id),
dataset_hash text NOT NULL,config jsonb NOT NULL DEFAULT '{}'::jsonb,config_hash text NOT NULL,
strattester_version text NOT NULL,status text NOT NULL DEFAULT 'BUILDING',
created_at timestamptz NOT NULL DEFAULT now(),started_at timestamptz,finished_at timestamptz,
last_error text)""",
"""CREATE TABLE IF NOT EXISTS research_shards(
id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
job_type text NOT NULL,shard_key text NOT NULL,input_spec jsonb NOT NULL,
input_hash text NOT NULL,status text NOT NULL DEFAULT 'queued',result_manifest jsonb,
result_hash text,created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
UNIQUE(run_id,shard_key))""",
"CREATE INDEX IF NOT EXISTS research_shards_status_idx ON research_shards(run_id,status,job_type,shard_key)"
]),
(38,"research_shard_dependencies",[
"""CREATE TABLE IF NOT EXISTS research_shard_dependencies(
run_id uuid NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
shard_id uuid NOT NULL REFERENCES research_shards(id) ON DELETE CASCADE,
depends_on_id uuid NOT NULL REFERENCES research_shards(id) ON DELETE CASCADE,
PRIMARY KEY(shard_id,depends_on_id),CHECK(shard_id<>depends_on_id))""",
"CREATE INDEX IF NOT EXISTS research_shard_deps_run_idx ON research_shard_dependencies(run_id,shard_id)"
]),
(39,"research_shard_failure_state",[
"ALTER TABLE research_shards ADD COLUMN IF NOT EXISTS last_error text"
]),
(40,"archive_compute_jobs",[
"""CREATE TABLE IF NOT EXISTS archive_compute_jobs(
id uuid PRIMARY KEY,symbol text NOT NULL,archive_date date NOT NULL,source_uri text NOT NULL,
expected_sha256 text,expected_bytes bigint,tick_size double precision NOT NULL,
status text NOT NULL DEFAULT 'queued',lease_owner text,lease_until timestamptz,
lease_generation integer NOT NULL DEFAULT 0,attempts integer NOT NULL DEFAULT 0,
max_attempts integer NOT NULL DEFAULT 5,result_manifest jsonb,result_hash text,last_error text,
created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
UNIQUE(symbol,archive_date))""",
"CREATE INDEX IF NOT EXISTS archive_compute_jobs_status_idx ON archive_compute_jobs(status,archive_date,symbol)"
]),
(41,"bounded_operational_retention",[
"CREATE INDEX IF NOT EXISTS ml_jobs_finished_idx ON ml_jobs(status,finished_at)",
"CREATE INDEX IF NOT EXISTS research_runs_finished_idx ON research_runs(status,finished_at)",
"CREATE INDEX IF NOT EXISTS archive_compute_jobs_updated_idx ON archive_compute_jobs(status,updated_at)"
]),
(42,"node_lifecycle",[
"""CREATE TABLE IF NOT EXISTS node_lifecycle(
node_id text PRIMARY KEY,state text NOT NULL DEFAULT 'ONLINE',
last_seen timestamptz,last_transition_at timestamptz NOT NULL DEFAULT now(),
quarantined_at timestamptz,decommissioned_at timestamptz,reason text,
updated_at timestamptz NOT NULL DEFAULT now())""",
"CREATE INDEX IF NOT EXISTS node_lifecycle_state_idx ON node_lifecycle(state,last_seen)"
]),
(43,"research_result_artifacts",[
"ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS aggregate_fingerprint text",
"ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS result_artifact_id uuid REFERENCES ml_artifacts(id)",
"CREATE INDEX IF NOT EXISTS research_runs_result_artifact_idx ON research_runs(result_artifact_id)"
])
]

async def apply_migrations(pool):
    async with pool.acquire() as c:
        await c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
        version bigint PRIMARY KEY,name text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())""")
        rows=await c.fetch("SELECT version FROM schema_migrations")
        done={r["version"] for r in rows}
        for version,name,sqls in MIGRATIONS:
            if version in done: continue
            async with c.transaction():
                for sql in sqls: await c.execute(sql)
                await c.execute("INSERT INTO schema_migrations(version,name) VALUES($1,$2)",version,name)
            log.info("migration applied",extra={"event":"migration","component":name})
