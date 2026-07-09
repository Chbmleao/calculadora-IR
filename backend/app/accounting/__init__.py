"""Bridge to the repo-root `core.py` (legacy "Bens e Direitos" logic).

WHY THIS FILE EXISTS
--------------------
`core.py` lives at the repository root, *outside* the `backend/` package tree, so
`import core` fails by default. The README requires reusing `core.py` UNCHANGED
(no vendoring / restructuring), so we make it importable by prepending the repo
root to `sys.path` here. Importing anything from `app.accounting` — which
`app.main` does on startup — guarantees `import core` works process-wide.

We also point `core`'s module-level `CATALOG_PATH` / `OVERRIDES_PATH` (which are
cwd-relative in the legacy module) at the configured catalog location, so
`core.load_catalog()` finds the xlsx no matter which directory uvicorn/pytest runs
from. The overrides file stays next to the catalog (accounting writes it via
`core.save_overrides`).

Later layers (task 07) import the accounting helpers from here.
"""

import sys
from pathlib import Path

# app/accounting/__init__.py -> parents: [1]=app, [2]=backend, [3]=repo root
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import core  # noqa: E402  (import after sys.path patch — intentional)

from app.config import get_settings  # noqa: E402


def _configure_core_paths() -> None:
    """Absolutize core's catalog/overrides paths from settings.CATALOG_PATH."""
    settings = get_settings()
    catalog = Path(settings.CATALOG_PATH)
    if not catalog.is_absolute():
        catalog = (_BACKEND_DIR / catalog).resolve()
    core.CATALOG_PATH = catalog
    core.OVERRIDES_PATH = catalog.parent / "cnpj_overrides.xlsx"


_configure_core_paths()

__all__ = ["core"]
