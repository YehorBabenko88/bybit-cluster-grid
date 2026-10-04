from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    role: str = "worker"
    coordinator_url: str = "http://127.0.0.1:8765"
    grid_shared_token: str = ""
    enrollment_token: str = ""
    node_credential: str = ""
    postgres_dsn: str = ""
    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    bybit_rest_url: str = "https://api.bybit.com"
    bybit_archive_base_url: str = "https://public.bybit.com/trading"
    archive_root: str = "C:/ProgramData/BybitClusterGrid/archive-cache"
    archive_probe_days: int = 30
    resource_cpu_limit: float = 75
    resource_ram_limit: float = 78
    resource_disk_free_gb: float = 25
    resource_reserve_cores: int = 2
    heartbeat_seconds: int = 10
    rebalance_seconds: int = 30
    assignment_max_churn_fraction: float = 0.10
    spool_max_gb: float = 8.0
    spool_critical_ratio: float = 0.90
    cluster_interval_seconds: int = 60
    microstructure_snapshot_ms: int = 250
    micro_tape_bucket_ms: int = 250
    micro_event_spool_max_gb: float = 4.0
    micro_raw_capture_enabled: bool = True
    micro_raw_orderbook_batch_ms: int = 250
    micro_max_symbols_per_node: int = 8
    micro_large_trade_mult: float = 5.0
    micro_large_trade_ema_alpha: float = 0.05
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""
    retention_enabled: bool = True
    retention_interval_minutes: int = 60
    retention_batch_size: int = 10000
    retention_market_events_days: int = 7
    retention_orderbook_snapshots_days: int = 14
    retention_footprint_days: int = 90
    retention_derivatives_days: int = 365
    retention_micro_raw_days: int = 30
    retention_micro_samples_days: int = 365
    strategy_cache_dir: str = "runtime_strategies"
    strategy_job_timeout_seconds: int = 21600
    strategy_cpu_soft_limit: float = 60
    strategy_ram_soft_limit: float = 72
    strategy_disk_free_gb: float = 30
    strategy_db_active_limit: int = 20
    strategy_poll_seconds: int = 3
    offline_warn_hours: int = 24
    quarantine_days: int = 3
    decommission_days: int = 7
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
