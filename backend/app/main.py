"""FastAPI application entry point.

Wires config -> CORS -> error handlers -> routers, and creates all DB tables on
startup. Business routers are added by later tasks; only `/api/health` exists now.

Importing `app.accounting` here activates the repo-root `core.py` import shim (see
`app/accounting/__init__.py`) so `import core` works everywhere the app runs.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import accounting  # noqa: F401  (activates the repo-root core.py import shim)
from app.api import register_routers
from app.api.common import register_exception_handlers
from app.config import get_settings
from app.db import init_db
from app.jobs.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: create the SQLite file + all tables, then start the auto-update
    # scheduler (task 13) unless disabled via RUN_SCHEDULER=0 (e.g. external cron).
    init_db()
    if settings.RUN_SCHEDULER:
        start_scheduler(settings.JOB_INTERVAL_HOURS)
    yield
    # Shutdown: stop the scheduler thread if we started one.
    shutdown_scheduler()


app = FastAPI(title="Investment Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Auto-include every app/api/<feature>.py that exposes a `router`, mounted under /api.
# Feature layers just drop in a new router file — no shared-wiring edits here — so
# parallel feature builds never collide on main.py. See app/api/__init__.py.
register_routers(app)
