# Task 08 — Frontend Scaffold (Vite + React + TS + Tailwind + API client)

- **Status:** Not started
- **Phase:** Frontend
- **Depends on:** 01 (a running API to point at)
- **Size:** M

## Context
The UI is React + Vite + TypeScript + Tailwind (README §3). This task sets up the app shell, styling,
routing, data‑fetching, and a typed API client so the page tasks (09–12) just build screens.

## Goal
A running `npm run dev` app (Vite, port 5173) with Tailwind configured, a nav layout, React Query
wired, an API client pointing at the backend via `VITE_API_BASE_URL`, shared formatting helpers, and
placeholder routes for Dashboard / Evolution / Rebalancing / Accounting / Import.

## Detailed spec

1. **Scaffold:** `npm create vite@latest frontend -- --template react-ts`. Add deps:
   `@tanstack/react-query`, `react-router-dom`, `recharts`, `axios` (or `fetch` wrapper),
   `clsx`. Dev: `tailwindcss postcss autoprefixer`.

2. **Tailwind:** init config, add directives to `src/index.css`, set a simple design token set
   (spacing, a neutral + one accent color, light/dark via `prefers-color-scheme`). Keep it clean and
   minimal — this is a personal dashboard.

3. **Routing** (`src/App.tsx`): `react-router` with a sidebar/nav layout (`src/components/Layout.tsx`)
   and routes: `/` (Dashboard), `/evolution`, `/rebalance`, `/accounting`, `/import`.

4. **Data layer:**
   - `src/lib/queryClient.ts` — React Query client; wrap app in `QueryClientProvider`.
   - `src/api/client.ts` — base client reading `import.meta.env.VITE_API_BASE_URL`
     (default `http://localhost:8000`). Central error handling (surface `{error}` messages via toast).
   - `src/api/types.ts` — TS types mirroring the backend Pydantic schemas (Position, PortfolioView,
     evolution points/metrics, rebalance rows, accounting rows). Keep in sync with `app/schemas.py`.
   - `src/api/hooks.ts` — typed React Query hooks: `usePositions`, `useEvolution`, `useRebalance`,
     `useTargets`, `useAccounting`, `useImportStatus`, mutations for import/refresh/save‑targets/save‑CNPJ.

5. **Formatting** (`src/lib/format.ts`): `formatBRL` (`R$ 1.234,56`, pt‑BR), `formatPct`,
   `formatDate`. Use everywhere money/%/dates render.

6. **Shell components:** `Layout` (nav + header showing "as of" date + a global "Refresh quotes"
   button wired to `POST /api/quotes/refresh`), `Card`, `StatTile`, `EmptyState`, `LoadingSpinner`,
   `ErrorBanner`. Placeholder page components render an `EmptyState` until tasks 09–12 fill them.

## Acceptance criteria
- [ ] `npm run dev` serves the app; Tailwind classes apply; light/dark both legible.
- [ ] Nav routes render placeholder pages; layout shows header + refresh button.
- [ ] `usePositions()` (or any hook) successfully calls the backend and renders JSON in a placeholder.
- [ ] `VITE_API_BASE_URL` configurable via `frontend/.env`; CORS works against the backend.
- [ ] Shared `formatBRL/formatPct/formatDate` helpers exist and are used.

## Out of scope
Real screens/charts (tasks 09–12).

## References
README §3, §7; backend schemas from tasks 04/05/06/07; `dataviz` skill for chart styling in 09–11.
