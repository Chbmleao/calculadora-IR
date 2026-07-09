"""Unit tests for the accounting (Bens e Direitos) layer — task 07.

These are pure unit tests: they call ``app.accounting.service`` directly against an
isolated in-memory SQLite session (never the app/TestClient, so a sibling feature
mid-write can't falsely fail them) with the real ``core.py`` and the real B3 sample
files. Everything is skipped gracefully if the sample xlsx are absent.

The core assertion mirrors the task's acceptance criteria: the JSON preview must
match what the legacy ``core`` logic produces from the same inputs (same count, same
Situação final / earnings per ticker), the ``.xlsx`` must open with the standard
columns, and saving a CNPJ override must be reflected by the next preview.
"""

from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.accounting import core, service
from app.ingestion import service as ingestion
from app.models import Base

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# backend/tests/test_accounting.py -> parents: [0]=tests, [1]=backend, [2]=repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_NEG_FILE = _REPO_ROOT / "input" / "negotiation_summary.xlsx"
_EARN_FILE = _REPO_ROOT / "input" / "earnings.xlsx"

_EXPECTED_COLUMNS = [
    "Produto",
    "Grupo",
    "Código",
    "CNPJ",
    "Discriminação",
    "Situação final",
    "Juros Sobre Capital Próprio",
    "Dividendo",
    "Rendimento",
]

_samples_available = _NEG_FILE.exists() and _EARN_FILE.exists()
_catalog_available = Path(core.CATALOG_PATH).exists()

pytestmark = pytest.mark.skipif(
    not (_samples_available and _catalog_available),
    reason="B3 sample xlsx (input/) and/or catalog (data/b3_enterprises.xlsx) absent",
)


@pytest.fixture(autouse=True)
def _isolate_catalog_cache():
    """Keep the module-level catalog cache from leaking across tests."""
    service._catalog_cached.cache_clear()
    yield
    service._catalog_cached.cache_clear()


@pytest.fixture()
def db() -> Session:
    """In-memory DB seeded from the real B3 samples via the ingestion pipeline."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    ingestion.import_file(session, "positions", _NEG_FILE.read_bytes(), _NEG_FILE.name)
    ingestion.import_file(session, "proventos", _EARN_FILE.read_bytes(), _EARN_FILE.name)
    try:
        yield session
    finally:
        session.close()


def _raw_assets() -> list[dict]:
    """The legacy path: build the assets straight from the xlsx via ``core``."""
    negotiation = core.read_negotiation_summary(str(_NEG_FILE))
    earnings = core.get_earnings(core.read_earnings(str(_EARN_FILE)))
    catalog = core.load_catalog()
    return core.get_assets_and_rights(negotiation, earnings, catalog)


def _fingerprint(asset: dict) -> tuple:
    return (
        asset["Produto"],
        asset["Grupo"],
        asset["Código"],
        asset["CNPJ"],
        asset["Discriminação"],
        round(float(asset["Situação final"]), 2),
        round(float(asset["Juros Sobre Capital Próprio"]), 2),
        round(float(asset["Dividendo"]), 2),
        round(float(asset["Rendimento"]), 2),
    )


def test_build_assets_matches_legacy_core(db: Session):
    """The imported-data preview equals what ``calculator.py``/``core`` produces."""
    imported = service.build_assets(db)
    raw = _raw_assets()

    assert len(imported) == len(raw)
    assert sorted(map(_fingerprint, imported)) == sorted(map(_fingerprint, raw))


def test_assets_have_core_columns(db: Session):
    assets = service.build_assets(db)
    assert assets, "expected at least one asset from the sample data"
    for asset in assets:
        assert list(asset.keys()) == _EXPECTED_COLUMNS


def test_known_ticker_situacao_final(db: Session):
    """A specific ticker's Situação final matches the legacy computation."""
    by_ticker = {a["Produto"]: a for a in service.build_assets(db)}
    raw_by_ticker = {a["Produto"]: a for a in _raw_assets()}
    ticker = "AAPL34"
    assert ticker in by_ticker
    assert by_ticker[ticker]["Situação final"] == pytest.approx(
        raw_by_ticker[ticker]["Situação final"]
    )


def test_xlsx_opens_with_expected_columns(db: Session):
    assets = service.build_assets(db)
    content = service.build_xlsx(assets)

    # Real xlsx magic bytes (PK zip header) + openpyxl round-trip.
    assert content[:2] == b"PK"
    frame = pd.read_excel(BytesIO(content))
    assert list(frame.columns) == _EXPECTED_COLUMNS
    assert len(frame) == len(assets)


def test_missing_cnpj_lists_uncatalogued_assets(db: Session):
    assets = service.build_assets(db)
    missing = service.missing_cnpj(assets)

    expected = {a["Produto"] for a in assets if a["CNPJ"] == "Não encontrado"}
    assert {m["Produto"] for m in missing} == expected
    assert expected, "sample data should include at least one missing-CNPJ asset"
    for item in missing:
        assert set(item.keys()) == {"Produto", "Grupo"}


def test_save_cnpj_persists_and_next_preview_reflects_it(db, tmp_path, monkeypatch):
    """Saving an override persists via core.save_overrides and shows up next preview."""
    overrides_path = tmp_path / "cnpj_overrides.xlsx"
    monkeypatch.setattr(core, "OVERRIDES_PATH", overrides_path)
    service._catalog_cached.cache_clear()

    # A ticker known to be missing from the catalog in the sample data.
    before = {a["Produto"]: a for a in service.build_assets(db)}
    ticker = "AAPL34"
    assert before[ticker]["CNPJ"] == "Não encontrado"

    new_cnpj = "12.345.678/0001-99"
    saved = service.save_cnpj([{"Ticker": ticker, "Tipo": "", "CNPJ": new_cnpj}])
    assert saved == 1
    assert overrides_path.exists()

    after = {a["Produto"]: a for a in service.build_assets(db)}
    assert after[ticker]["CNPJ"] == new_cnpj
    assert ticker not in {m["Produto"] for m in service.missing_cnpj(list(after.values()))}


def test_save_cnpj_drops_blank_rows(db, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OVERRIDES_PATH", tmp_path / "cnpj_overrides.xlsx")
    service._catalog_cached.cache_clear()

    saved = service.save_cnpj(
        [
            {"Ticker": "AAAA3", "Tipo": "", "CNPJ": "   "},
            {"Ticker": "BBBB4", "Tipo": "", "CNPJ": "11.111.111/0001-11"},
        ]
    )
    assert saved == 1
