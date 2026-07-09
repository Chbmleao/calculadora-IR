"""SQLAlchemy engine, session factory, and the FastAPI `get_db` dependency.

Relative sqlite paths in DATABASE_URL are resolved against the `backend/` directory
(not the process cwd) and the parent folder is created, so `backend/data/app.db`
exists regardless of where uvicorn/pytest is launched from. Call `init_db()` on
startup to create all tables.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

# backend/app/db.py -> parents[1] = backend/
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_SQLITE_PREFIX = "sqlite:///"


def _resolve_database_url(url: str) -> str:
    """Absolutize a relative sqlite file path against backend/ and ensure its dir exists."""
    if not url.startswith(_SQLITE_PREFIX):
        return url
    raw_path = url[len(_SQLITE_PREFIX):]
    if not raw_path or raw_path == ":memory:":
        return url
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = (_BACKEND_DIR / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"{_SQLITE_PREFIX}{db_path}"


def _make_engine():
    settings = get_settings()
    url = _resolve_database_url(settings.DATABASE_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables (idempotent — safe to call on every startup)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session and always closing it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
