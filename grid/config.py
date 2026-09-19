from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    role: str = "worker"
    coordinator_url: str = "http://127.0.0.1:8787"
    grid_shared_token: str
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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
