"""Application settings loaded from the repo-root `.env` via pydantic-settings.

The `.env` lives at the repository root (one level above `backend/`) so the same
file configures the legacy tool and this backend. Every setting has a safe default
so the app boots even without a `.env`. Use `get_settings()` (cached) everywhere —
never instantiate `Settings()` directly.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[0]=app, [1]=backend, [2]=repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        # `.env` also holds frontend + later-task keys (TARGET_ALLOCATIONS, etc.);
        # ignore anything this layer does not declare.
        extra="ignore",
    )

    # SQLite (or any SQLAlchemy URL). Relative sqlite paths resolve against backend/.
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # brapi.dev quote provider (task 03). Empty token => tokenless / yfinance-only.
    BRAPI_TOKEN: str = ""
    BRAPI_BASE_URL: str = "https://brapi.dev/api"

    # Comma-separated CORS origins for the frontend dev server.
    CORS_ORIGINS: str = "http://localhost:5173"

    # Ticker -> Tipo/CNPJ catalog reused from the legacy tool (relative to backend/).
    CATALOG_PATH: str = "../data/b3_enterprises.xlsx"

    # How long a cached "latest" quote stays fresh (task 03).
    QUOTE_CACHE_TTL_MINUTES: int = 60

    # Auto-update job (task 13): an in-process APScheduler runs the daily refresh +
    # snapshot every JOB_INTERVAL_HOURS. Set RUN_SCHEDULER=0 to disable (e.g. drive
    # POST /api/jobs/run-daily from an external cron instead).
    RUN_SCHEDULER: bool = True
    JOB_INTERVAL_HOURS: int = 12

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS parsed into a list (comma-separated in the env)."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide, cached Settings instance."""
    return Settings()
