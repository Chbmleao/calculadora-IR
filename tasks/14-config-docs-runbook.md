# Task 14 — Config, Docs & Run Scripts

- **Status:** Not started
- **Phase:** Polish
- **Depends on:** all
- **Size:** S

## Context
Final wiring so a fresh clone runs end‑to‑end with a documented setup. Ties together the env vars,
run scripts, and a user‑facing guide covering both the new dashboard and the legacy IR tool.

## Goal
Complete `.env.example`, a root README section for the new app, a runbook (get a brapi token → import
your B3 exports → set targets → view dashboard), and one‑command dev/start scripts.

## Detailed spec

1. **`.env.example`** — every variable with a comment and a sensible default:
   `DATABASE_URL`, `BRAPI_TOKEN` (+ where to get it: brapi.dev signup), `BRAPI_BASE_URL`,
   `CORS_ORIGINS`, `CATALOG_PATH`, `QUOTE_CACHE_TTL_MINUTES`, `TARGET_ALLOCATIONS` (JSON example),
   scheduler settings (task 13), `VITE_API_BASE_URL` (frontend).

2. **README (root):** add a "Investment Dashboard (MVP)" section: architecture diagram (README §3),
   how to run backend + frontend (`make dev`), and the data‑import runbook:
   1) download the three B3 exports (Resumo de Negociação, histórico de Negociação, Proventos);
   2) upload them in `/import`; 3) optionally add a brapi token for higher limits;
   4) set target allocation in `/rebalance`; 5) view Dashboard/Evolution.
   Keep the existing legacy IR docs; note the legacy Streamlit app still works.

3. **Data source note:** briefly document why prices come from brapi/yfinance and that the B3 investor
   API is a Phase‑2 (institutional) option — so future readers don't re‑investigate. Link to
   `tasks/README.md` §2.

4. **Run scripts:** finalize the `Makefile`/scripts from task 00 (`dev`, `backend`, `frontend`, `test`,
   plus `seed-targets` if useful). Ensure `make dev` brings up both servers.

5. **Sanity checklist (manual):** a short "smoke test" list — import samples from `input/`, verify
   dashboard totals, evolution renders, rebalance suggests buys, accounting downloads xlsx.

## Acceptance criteria
- [ ] Fresh clone → follow README → app runs with `make dev`; both servers reachable.
- [ ] `.env.example` documents every variable used anywhere in the codebase.
- [ ] README explains import → targets → dashboard, and the B3‑API Phase‑2 note.
- [ ] Manual smoke checklist passes against the real `input/` samples.

## Out of scope
Deployment/hosting, CI, auth (all post‑MVP).

## References
All prior tasks; README §2, §3, §7.
