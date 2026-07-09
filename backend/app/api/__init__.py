"""API router registry.

Auto-includes every ``app/api/<feature>.py`` module that exposes a module-level
``router`` (an ``APIRouter``), mounting them all under the ``/api`` prefix.

Each feature module defines full sub-paths on its own router (e.g.
``@router.get("/portfolio/positions")``) and owns its own file. ``main.py`` calls
``register_routers(app)`` once at startup. This means a new feature layer only
adds a new router file — it never edits shared wiring here or in ``main.py`` — so
independent feature layers can be built in parallel without colliding.
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI

# Modules in this package that are not feature routers.
_SKIP = {"common"}


def register_routers(app: FastAPI) -> None:
    """Import every feature module under ``app.api`` and include its ``router``."""
    from app import api as api_pkg

    for mod in pkgutil.iter_modules(api_pkg.__path__):
        if mod.name.startswith("_") or mod.name in _SKIP:
            continue
        module = importlib.import_module(f"app.api.{mod.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router, prefix="/api")
