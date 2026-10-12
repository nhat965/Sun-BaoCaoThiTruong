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
    market_provider_priority: str = "yahoo"
    fireant_base_url: str = "https://api.fireant.vn"
    fireant_access_token: str | None = None
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
