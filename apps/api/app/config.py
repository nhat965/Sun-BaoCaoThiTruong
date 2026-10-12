from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./market_intelligence.db"
    market_data_mode: str = "live"
    web_origin: str = "http://localhost:3000"
    request_timeout_seconds: float = 12
    market_provider_priority: str = "yahoo"
    fireant_base_url: str = "https://api.fireant.vn"
    fireant_access_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
