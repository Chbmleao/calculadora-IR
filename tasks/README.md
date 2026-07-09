# Calculadora-IR → Investment Dashboard — MVP Task Plan

This folder is the build plan for turning the existing **Calculadora IR** Python script into a
personal **investment dashboard + IR (income‑tax) helper** with a React/Tailwind UI.

Each `NN-*.md` file is a **self‑contained task** written so that an independent agent (or developer)
can pick it up and implement it with minimal extra context. Read this README first, then your task file.

---

## 1. Product vision (MVP)

A single‑user (no login) web app for a Brazilian retail investor holding B3 assets (ações, FIIs,
ETFs, BDRs) that:

1. **Positions & allocation** — shows current holdings, market value, and the **% weight** of each
   asset and asset class in the portfolio.
2. **Patrimony evolution & rentability** — charts total patrimony over time and separates *money you
   added* (contributions) from *market gains* to show **true return**.
3. **Target allocation & rebalancing** — lets the investor define a desired % per asset/class and
   shows what to **buy** to reach the target.
4. **Accounting (Bens e Direitos)** — the existing IR feature: generate the DIRPF “Bens e Direitos”
   sheet. **Reuses `core.py` as‑is.**
5. **Automatic updates** — position quantities come from B3 broker exports; **prices refresh
   automatically** from a quote API so values stay current.

MVP constraints: **no authentication**, single user, all secrets/config in a `.env` file.

---

## 2. Feasibility findings (already researched — do not re‑investigate)

**B3 “Área do Investidor” API — NOT used in the MVP (verified against B3 primary sources).**
It is a B2B, contract‑gated institutional API. Verified facts:
- **CPF‑only individual (pessoa física): zero access** — not even the free sandbox. B3 states: *“Não
  oferecemos acesso direto às APIs para pessoas físicas … exclusivamente destinadas ao consumo de
  clientes B2B.”* The sandbox self‑service **rejects requests without a valid CNPJ** (`documento` field).
- **With a CNPJ (e.g. an MEI):** you can self‑provision the **sandbox — synthetic data only** — and are
  *formally* eligible to contract production, but production still requires a signed license, passing
  B3’s **self‑assessment + SecurityScorecard** cyber review (refusable at B3’s discretion), and a
  **R$6,000/yr floor (R$500/mo min)**, billed per consenting investor.
- **No “pull my own portfolio” endpoint exists.** Production data is *third‑party investors who consent*
  to a licensed fintech — the individual‑investor use case is served only by the web UI at
  `investidor.b3.com.br`. So even incorporating does not yield a clean personal‑data API.
- It returns positions/trades/proventos at **D‑1** — **not** market quotes.

Treat it as a **Phase‑2** option only, and even then as a fintech‑aggregation feature (not a personal
data pull). Do not build against it now. The realistic input path is **user‑uploaded B3 Excel exports**.

**Prices come from public quote APIs** behind a provider interface (see `03-quote-service.md`):
- **Primary: brapi.dev** — native B3 tickers (`PETR4`, `MXRF11`, `AAPL34`), free 15k req/mo, current
  quotes, **1‑year** history on the free tier. Free token required.
- **Fallback + long history: yfinance** — append `.SA` (`PETR4.SA`), no key, **multi‑year** daily
  history, but unofficial/fragile → cache aggressively.
- **Local SQLite cache** of daily closes keyed by `(ticker, date)` is mandatory (cuts request counts,
  survives outages).
- Upgrade path: **brapi Pro** (~R$117/mo, 10+ yr history) is a config swap, not a rewrite.

---

## 3. Architecture & stack (decided)

```
┌────────────────────────┐        HTTP/JSON        ┌──────────────────────────┐
│  Frontend (React)      │  ───────────────────▶  │  Backend (FastAPI)       │
│  Vite + TS + Tailwind  │  ◀───────────────────  │  Python 3.11+            │
│  Recharts, React Query │                         │  pandas, openpyxl        │
└────────────────────────┘                         │  reuses core.py          │
                                                    │  brapi + yfinance quotes │
                                                    │  SQLite (file DB)        │
                                                    └──────────────────────────┘
```

- **Backend:** FastAPI. Reuses the existing `core.py` accounting logic **unchanged**. Adds Excel
  importers, a quote service, portfolio math, and a SQLite store.
- **Frontend:** React + Vite + TypeScript + Tailwind. Charts via **Recharts**. Server state via
  **@tanstack/react-query**.
- **Persistence:** SQLite (single file, e.g. `backend/data/app.db`). Zero‑config, fits single‑user MVP.
- **No auth.** Config via `.env`.

### Target repo layout (created in task 00)

```
calculadora-IR/
├── core.py                     # EXISTING — reused untouched by the backend
├── calculator.py               # EXISTING — legacy CLI (leave as-is)
├── app.py                      # EXISTING — legacy Streamlit app (leave as-is)
├── data/b3_enterprises.xlsx    # EXISTING — ticker→CNPJ catalog
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app + router wiring
│   │   ├── config.py           # settings from .env
│   │   ├── db.py               # SQLite engine/session
│   │   ├── models.py           # ORM tables
│   │   ├── schemas.py          # Pydantic response models
│   │   ├── ingestion/          # Excel importers (wrap core.py readers)
│   │   ├── quotes/             # brapi + yfinance providers + cache
│   │   ├── portfolio/          # positions, evolution, rebalancing logic
│   │   ├── accounting/         # thin wrapper over core.py
│   │   └── api/                # route modules per domain
│   ├── tests/
│   ├── pyproject.toml / requirements.txt
│   └── data/app.db             # gitignored
├── frontend/
│   ├── src/{pages,components,lib,api}/
│   ├── index.html, vite.config.ts, tailwind.config.js
│   └── package.json
├── .env.example
└── tasks/                      # THIS FOLDER
```

> Keep the legacy `app.py` / `calculator.py` working; the new backend imports `core.py` directly.
> Do **not** rewrite the tax rules.

---

## 4. B3 data sources (the app’s inputs)

All are Excel files the user downloads from investidor.b3.com.br. Real samples live in `input/` and
`data/`. **Schemas are authoritative — an agent must code against these exact column names.**

| File (sample) | Sheet | Columns (used) | Feeds |
|---|---|---|---|
| `data/b3_enterprises.xlsx` | `Página1` | `Ticker`, `Tipo`, `CNPJ` (910 rows) | catalog / accounting |
| `input/earnings.xlsx` (Proventos) | `Proventos Recebidos` | `Produto`, `Pagamento`, `Tipo de Evento`, `Instituição`, `Quantidade`, `Preço unitário`, `Valor líquido` | income, accounting |
| `input/negotiation_summary.xlsx` (Resumo) | `Negociação - Resumo` | `Código de Negociação`, `Período (Inicial)`, `Período (Final)`, `Instituição`, `Quantidade (Compra)`, `Quantidade (Venda)`, `Quantidade (Líquida)`, `Preço Médio (Compra)`, `Preço Médio (Venda)` | positions, targets, accounting |
| `input/negociacao-*.xlsx` (histórico) | `Negociação` | `Data do Negócio`, `Tipo de Movimentação` (Compra/Venda), `Mercado` (à Vista / Fracionário), `Prazo/Vencimento`, `Instituição`, `Código de Negociação`, `Quantidade`, `Preço`, `Valor` | **evolution reconstruction** |

Key domain rules (already implemented in `core.py`):
- **Fractional tickers** end in `F` (e.g. `ITSA4F`) → normalize to the standard ticker (`ITSA4`).
- **Proventos** counted: `Rendimento`, `Juros Sobre Capital Próprio`, `Dividendo`.
- **Classification by suffix:** ends `11` → Fundos (FII, or ETF for `IVVB11`/`SMAL11`); ends `34` →
  BDR; else → Ação. See `get_product_group` / `get_product_code` in `core.py`.

---

## 5. Existing code to reuse (`core.py`)

| Function | Reuse in |
|---|---|
| `load_catalog()`, `save_overrides()` | ingestion, accounting, quotes (ticker→Tipo/CNPJ) |
| `read_earnings()`, `get_earnings()` | proventos ingestion |
| `read_negotiation_summary()` | positions ingestion |
| `get_assets_and_rights()`, `build_output_xlsx_bytes()` | accounting endpoint |
| `get_product_group/code/cnpj`, `get_discrimination` | classification helpers |

The new backend should **import these**, not reimplement them.

---

## 6. Task index & build order

Dependency‑ordered. `→` means “depends on”.

| # | Task | Depends on |
|---|---|---|
| 00 | Project scaffold & repo layout | — |
| 01 | Backend foundation (FastAPI, config, SQLite, conventions) | 00 |
| 02 | Data ingestion (Excel importers + catalog + upload) | 01 |
| 02b | Manual trade entry (**optional** add-on; extends 02) | 01, 02 |
| 03 | Quote service (brapi + yfinance + cache) | 01 |
| 04 | Positions & allocation (domain + endpoints) | 02, 03 |
| 05 | Patrimony evolution & rentability (reconstruction) | 02, 03 |
| 06 | Target allocation & rebalancing | 04 |
| 07 | Accounting — Bens e Direitos (wrap core.py) | 02 |
| 08 | Frontend scaffold (Vite/React/TS/Tailwind + API client) | 01 |
| 09 | Dashboard UI (positions + allocation) | 04, 08 |
| 10 | Evolution UI (chart + rentability) | 05, 08 |
| 11 | Rebalancing UI | 06, 08 |
| 12 | Accounting UI (preview/download + CNPJ editor) | 07, 08 |
| 13 | Auto‑update & refresh (quotes + daily snapshot) | 03, 04, 05 |
| 14 | Config, docs & run scripts | all |

Rough critical path: 00 → 01 → (02 ∥ 03) → (04 ∥ 05) → 06 → UI tasks.

---

## 7. Conventions (apply in every task)

- **Money:** store/compute in `Decimal` or float with 2‑dp rounding (`REAL_DECIMAL_PLACES = 2`, as in
  `core.py`); format in UI as `R$ 1.234,56` (pt‑BR).
- **Tickers:** canonical = uppercase, no `F` suffix. Normalize on ingest.
- **Dates:** B3 exports use `DD/MM/YYYY`; store as ISO `YYYY-MM-DD`.
- **API responses:** JSON; wrap errors as `{ "error": "message" }` with proper HTTP status.
- **No secrets in code:** brapi token, DB path, CORS origins, target allocations → `.env`
  (`.env.example` documents them).
- **Tests:** each backend domain task ships pytest unit tests using the real sample files in `input/`.

## 8. Glossary

- **Provento** — income event (dividend / JCP / rendimento).
- **JCP** — Juros Sobre Capital Próprio (interest on equity).
- **Bens e Direitos** — DIRPF form section listing assets. The legacy feature.
- **Preço Médio (Compra)** — cumulative average purchase price = cost basis.
- **Rentability / rentabilidade** — return; MVP computes both simple return and a
  time‑weighted return (TWR) that removes the effect of contributions.
