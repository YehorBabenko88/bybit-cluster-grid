from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    role: str = "worker"
    coordinator_url: str = "http://127.0.0.1:8787"
    grid_shared_token: str = ""\n    enrollment_token: str = ""\n    node_credential: str = ""
    postgres_dsn: str
    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    bybit_rest_url: str = "https://api.bybit.com"
    resource_cpu_limit: float = 75
    resource_ram_limit: float = 78
    resource_disk_free_gb: float = 25
    resource_reserve_cores: int = 2
    heartbeat_seconds: int = 10
    rebalance_seconds: int = 30
    cluster_interval_seconds: int = 60
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""
    retention_enabled: bool = True
    retention_interval_minutes: int = 60
    retention_batch_size: int = 10000
    retention_market_events_days: int = 7
    retention_orderbook_snapshots_days: int = 14
    retention_footprint_days: int = 90
    retention_derivatives_days: int = 365
    strategy_cache_dir: str = "runtime_strategies"
    strategy_job_timeout_seconds: int = 21600
    strategy_cpu_soft_limit: float = 60
    strategy_ram_soft_limit: float = 72
    strategy_disk_free_gb: float = 30
    strategy_db_active_limit: int = 20
    strategy_poll_seconds: int = 3
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
