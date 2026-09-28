from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    sectors_api_key: str
    supabase_url: str
    supabase_service_role_key: str
    admin_secret: str = "changeme"
    cors_origins: str = "http://localhost:5173"
    enable_scheduler: bool = False

    # Ollama Cloud powers the AI market brief. The key authenticates direct
    # requests to ollama.com; base URL and model can be overridden per-env.
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:20b"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
