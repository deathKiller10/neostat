from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Neon (and most Postgres hosts) hand out postgres:// or postgresql://, but
    SQLAlchemy needs an explicit driver. Rewrite to the psycopg v3 driver so a
    connection string can be pasted verbatim from the Neon dashboard. Non-Postgres
    URLs (e.g. sqlite:// used in tests and local dev) pass through untouched.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./local_dev.db"

    google_api_key: str = ""
    ocr_provider: str = "tesseract"
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"

    max_upload_mb: int = 10
    max_page_count: int = 3

    validation_abs_tol: float = 1.00
    validation_rel_tol: float = 0.005

    sample_run_delay_seconds: float = 6.0

    cors_allow_origins: str = "*"

    @property
    def sqlalchemy_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
