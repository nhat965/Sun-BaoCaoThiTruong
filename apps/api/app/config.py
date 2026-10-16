from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./market_intelligence.db"
    app_environment: str = "development"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    market_data_mode: str = "live"
    web_origin: str = "http://localhost:3000"
    request_timeout_seconds: float = 12
    market_provider_priority: str = "vnstock,ssi_fastconnect,yahoo"
    fireant_base_url: str = "https://api.fireant.vn"
    fireant_access_token: str | None = None
    ssi_base_url: str = "https://api.ssi.com.vn"
    # Official SSI FastConnect Data host used by the published Python SDK.
    ssi_data_base_url: str = "https://fc-data.ssi.com.vn/"
    ssi_auth_url: str = "https://api.ssi.com.vn/api/v3/auth/token"
    ssi_environment: str = "production"
    ssi_api_key: str | None = None
    ssi_api_secret: str | None = None
    # Must be copied from an approved SSI contract; there is intentionally no default.
    ssi_ohlc_endpoint_template: str | None = None
    # Vnstock is an optional client over an entitled upstream source. Keep the
    # selected route explicit so fallback responses are never mislabeled.
    vnstock_market_source: str = "vci"
    vnstock_reference_source: str = "vci"
    fiingroup_base_url: str | None = None
    fiingroup_api_key: str | None = None
    fiingroup_financial_endpoint_template: str | None = None
    fiingroup_rights_confirmed: bool = False
    financial_csv_url_template: str | None = None
    financial_csv_allowed_hosts: str = ""
    financial_csv_bearer_token: str | None = None
    financial_csv_rights_confirmed: bool = False
    financial_csv_max_bytes: int = 5_000_000
    financial_csv_retries: int = 1
    admin_api_token: str | None = None
    reader_api_token: str | None = None
    admin_rate_limit_per_minute: int = 30
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 60
    market_cache_ttl_seconds: int = 300
    news_feeds: str = "https://vnexpress.net/rss/kinh-doanh.rss"
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    analyst_timeout_seconds: float = 20
    llm_rate_limit_per_minute: int = 10
    automation_max_retries: int = 3
    automation_lease_seconds: int = 1800
    market_timezone: str = "Asia/Ho_Chi_Minh"
    # Scheduler is opt-in. The standalone worker reads these values; FastAPI never
    # starts a background loop implicitly.
    scheduler_enabled: bool = False
    scheduler_poll_interval_seconds: int = 30
    scheduler_daily_times: str = "16:30"
    scheduler_max_concurrency: int = 1
    scheduler_batch_limit: int = 50
    max_request_bytes: int = 5_000_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_environment.lower() in {"production", "prod"}:
            if not self.admin_api_token or len(self.admin_api_token) < 24:
                raise ValueError("ADMIN_API_TOKEN must be configured with at least 24 characters in production")
            if "*" in {host.strip() for host in self.allowed_hosts.split(",")}:
                raise ValueError("ALLOWED_HOSTS must not contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
