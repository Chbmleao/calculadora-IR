# Task 00 — Project Scaffold & Repo Layout

- **Status:** Not started
- **Phase:** Foundations
- **Depends on:** —
- **Size:** S

## Context
The repo currently holds the legacy Python IR tool (`core.py`, `app.py`, `calculator.py`, `data/`).
We are adding a FastAPI backend and a React frontend **without disturbing** the legacy tool. Read
`tasks/README.md` §3 for the target layout and stack decisions.

## Goal
Create the folder structure, tooling, and env scaffolding for `backend/` and `frontend/`, plus root
run‑scripts, so subsequent tasks have a place to write code and a one‑command dev workflow.

## Detailed spec

1. **Directories:** create `backend/app/{ingestion,quotes,portfolio,accounting,api}`,
   `backend/tests`, `backend/data/` (gitignored), and `frontend/` (populated in task 08).

2. **Backend tooling:** `backend/requirements.txt` (list from task 01) + a `backend/README.md` with
   run instructions. Keep the legacy root `requirements.txt` as‑is (Streamlit tool still works).

3. **Root run‑scripts:** add a `Makefile` (or `package.json` scripts / `justfile`) at repo root:
   - `make backend` → `uvicorn app.main:app --reload` (from `backend/`)
   - `make frontend` → `npm run dev` (from `frontend/`)
   - `make dev` → run both (e.g. via `concurrently` or two shells)
   - `make test` → backend `pytest`

4. **Env:** create `.env.example` at repo root documenting **every** variable used across tasks
   (DATABASE_URL, BRAPI_TOKEN, BRAPI_BASE_URL, CORS_ORIGINS, CATALOG_PATH, QUOTE_CACHE_TTL_MINUTES,
   TARGET_ALLOCATIONS). Backend loads `.env`; frontend uses `VITE_API_BASE_URL` in `frontend/.env`.

5. **.gitignore:** append `backend/data/*.db`, `backend/__pycache__/`, `frontend/node_modules/`,
   `frontend/dist/`, `.env`. Keep existing ignores.

6. **Monorepo tooling note (Turborepo):** the MVP is one Python backend + one React app, so
   **Turborepo is intentionally not used** (it manages JS/TS packages only and would add config with
   no payoff for a single frontend). If the project later goes full‑TypeScript or the frontend splits
   into multiple JS packages, adding Turborepo/npm‑workspaces is a small, non‑breaking change — leave a
   `TODO(turborepo)` note in the root README describing this trigger so the decision is easy to revisit.

## Acceptance criteria
- [ ] `backend/` and `frontend/` trees exist per README §3; legacy files untouched and still runnable.
- [ ] `.env.example` lists all variables; `.gitignore` updated.
- [ ] `make backend` / `make frontend` / `make dev` / `make test` targets exist (may no‑op until 01/08).
- [ ] Root `README.md` (or `backend/README.md`) documents how to run each part, and the Turborepo trigger note.

## Out of scope
Actual app code (tasks 01+/08+).

## References
README §3 (layout), task 01 (backend deps), task 08 (frontend deps).
