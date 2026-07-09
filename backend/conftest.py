"""Ensure the `backend/` directory is importable so tests can `import app.*`.

pytest normally handles this via rootdir insertion; this makes it explicit and
robust regardless of how pytest is invoked.
"""

import os
import sys
from pathlib import Path

# Never spawn the background scheduler thread during tests (task 13). Tests that
# exercise the scheduler call it directly. Set before Settings is first read/cached.
os.environ.setdefault("RUN_SCHEDULER", "0")

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
