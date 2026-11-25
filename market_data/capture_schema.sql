
CREATE TABLE IF NOT EXISTS market_data_capture_v2 (
    observation_sha256 text PRIMARY KEY,
    observation_bytes bytea NOT NULL,
    payload_bytes bytea,
    connection_id text NOT NULL,
    observation_index bigint NOT NULL,
    UNIQUE(connection_id, observation_index)
)
;
CREATE TABLE IF NOT EXISTS market_data_execution_v1 (
    event_key text PRIMARY KEY, symbol text NOT NULL, timestamp_us numeric(19,0) NOT NULL,
    price text NOT NULL, quantity text NOT NULL, side text NOT NULL,
    trade_id text NOT NULL, content_sha256 text NOT NULL
);
CREATE TABLE IF NOT EXISTS market_data_archive_checkpoint_v1 (
    import_id text PRIMARY KEY, blob_sha256 text NOT NULL, committed_rows bigint NOT NULL,
    last_observation_sha256 text NOT NULL, total_rows bigint NOT NULL,
    last_timestamp_us text NOT NULL, last_trade_id text NOT NULL
);
