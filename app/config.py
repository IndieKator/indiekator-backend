from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    sectors_api_key: str
    supabase_url: str
    supabase_service_role_key: str
    admin_secret: str = "changeme"
    cors_origins: str = "http://localhost:5173"
    idx_cf_clearance: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
