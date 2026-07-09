"""Unit tests for the quote service (task 03).

Providers are mocked so no test touches the network (except the opt-in brapi
integration test, skipped unless ``RUN_BRAPI_INTEGRATION`` is set). We build an
isolated in-memory SQLite DB per test rather than the app's file DB, and never
construct the FastAPI app/TestClient (sibling feature layers may be mid-write).

Covers the acceptance criteria: brapi→yfinance fallback, a single unknown ticker
not crashing the batch, cache-hit-avoids-network, and delta-fetch-only-missing.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, PositionSummary, Transaction
from app.quotes import cache
from app.quotes.base import DailyClose, ProviderError, Quote, canonical_ticker, to_money
from app.quotes.brapi import BrapiProvider
from app.quotes.cache import CacheRow
from app.quotes.service import QuoteService, get_portfolio_tickers
from app.quotes.yfinance_provider import YFinanceProvider


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# --------------------------------------------------------------------------- #
# Test doubles                                                                 #
# --------------------------------------------------------------------------- #


class StubResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class StubHttp:
    """Stands in for an httpx.Client; records calls, returns a canned response."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._response


class RecordingProvider:
    """A QuoteProvider stub that records calls and returns canned data."""

    def __init__(self, name, *, latest_map=None, history_map=None, raises=None):
        self.name = name
        self._latest_map = latest_map or {}
        self._history_map = history_map or {}
        self._raises = raises
        self.latest_calls = []
        self.history_calls = []

    def latest(self, tickers):
        self.latest_calls.append(list(tickers))
        if isinstance(self._raises, Exception):
            raise self._raises
        return {t: self._latest_map[t] for t in tickers if t in self._latest_map}

    def history(self, ticker, start, end):
        self.history_calls.append((ticker, start, end))
        if isinstance(self._raises, Exception):
            raise self._raises
        rows = self._history_map.get(ticker, [])
        return [dc for dc in rows if start <= dc.date <= end]


class ExplodingProvider:
    """Fails the test loudly if any method is called (proves 'no network')."""

    name = "exploding"

    def latest(self, tickers):
        raise AssertionError("latest() should not have been called")

    def history(self, ticker, start, end):
        raise AssertionError("history() should not have been called")


class FakeTicker:
    def __init__(self, frame):
        self._frame = frame

    def history(self, **kwargs):
        return self._frame


# --------------------------------------------------------------------------- #
# Helpers / value objects                                                      #
# --------------------------------------------------------------------------- #


def test_canonical_ticker_normalizes():
    assert canonical_ticker(" petr4 ") == "PETR4"
    assert canonical_ticker("ITSA4F") == "ITSA4"
    assert canonical_ticker("mxrf11") == "MXRF11"
    assert canonical_ticker("aapl34") == "AAPL34"


def test_to_money_rounds_to_2dp():
    assert to_money(33.449) == Decimal("33.45")
    assert to_money("10") == Decimal("10.00")
    assert to_money(Decimal("1.005")) == Decimal("1.01")


# --------------------------------------------------------------------------- #
# Cache                                                                        #
# --------------------------------------------------------------------------- #


def test_cache_upsert_and_history_roundtrip(db):
    rows = [
        CacheRow("PETR4", date(2024, 1, 2), Decimal("30.00"), "brapi"),
        CacheRow("PETR4", date(2024, 1, 3), Decimal("31.00"), "brapi"),
    ]
    assert cache.upsert(db, rows) == 2

    hist = cache.get_cached_history(db, "petr4", date(2024, 1, 1), date(2024, 1, 31))
    assert [dc.date for dc in hist] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert hist[0].close == Decimal("30.00")

    latest = cache.get_latest_cached(db, "PETR4")
    assert latest is not None and latest.date == date(2024, 1, 3)

    # Upsert an existing key updates in place (still one row for that date).
    assert cache.upsert(db, [CacheRow("PETR4", date(2024, 1, 3), Decimal("32.50"), "yfinance")]) == 1
    reread = cache.get_cached_history(db, "PETR4", date(2024, 1, 3), date(2024, 1, 3))
    assert reread[0].close == Decimal("32.50")


def test_is_fresh_within_ttl():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert cache.is_fresh(now - timedelta(minutes=5), ttl_minutes=60) is True
    assert cache.is_fresh(now - timedelta(minutes=90), ttl_minutes=60) is False
    assert cache.is_fresh(None, ttl_minutes=60) is False
    # Aware datetimes are handled too.
    assert cache.is_fresh(datetime.now(timezone.utc), ttl_minutes=60) is True


# --------------------------------------------------------------------------- #
# brapi provider (mocked HTTP)                                                 #
# --------------------------------------------------------------------------- #


def test_brapi_latest_parses_results():
    payload = {
        "results": [
            {
                "symbol": "PETR4",
                "regularMarketPrice": 33.45,
                "regularMarketTime": "2024-05-31T20:07:00.000Z",
            }
        ]
    }
    http = StubHttp(StubResponse(200, payload))
    provider = BrapiProvider("https://brapi.dev/api", token="tok", client=http)

    quotes = provider.latest(["PETR4"])
    assert quotes["PETR4"] == Quote(Decimal("33.45"), date(2024, 5, 31), "brapi")
    # Token sent both as header and query param.
    assert http.calls[0]["headers"]["Authorization"] == "Bearer tok"
    assert http.calls[0]["params"]["token"] == "tok"


def test_brapi_history_filters_to_range():
    def epoch(y, m, d):
        return int(datetime(y, m, d, 12, tzinfo=timezone.utc).timestamp())

    payload = {
        "results": [
            {
                "historicalDataPrice": [
                    {"date": epoch(2024, 1, 2), "close": 10.0},
                    {"date": epoch(2024, 1, 3), "close": 11.0},
                    {"date": epoch(2024, 1, 10), "close": 15.0},
                ]
            }
        ]
    }
    provider = BrapiProvider("https://brapi.dev/api", token="tok", client=StubHttp(StubResponse(200, payload)))
    hist = provider.history("PETR4", date(2024, 1, 1), date(2024, 1, 3))
    assert [dc.date for dc in hist] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert hist[0].close == Decimal("10.00")


def test_brapi_raises_on_rate_limit():
    provider = BrapiProvider("https://brapi.dev/api", token="tok", client=StubHttp(StubResponse(429, {})))
    with pytest.raises(ProviderError) as exc:
        provider.latest(["PETR4"])
    assert exc.value.status_code == 429


def test_brapi_raises_on_unauthorized():
    provider = BrapiProvider("https://brapi.dev/api", token="", client=StubHttp(StubResponse(401, {})))
    with pytest.raises(ProviderError) as exc:
        provider.history("PETR4", date(2024, 1, 1), date(2024, 1, 2))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------- #
# yfinance provider (mocked Ticker)                                            #
# --------------------------------------------------------------------------- #


def test_yfinance_history_extracts_close():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame({"Open": [1, 2, 3], "Close": [10.0, 11.5, 12.25]}, index=idx)
    provider = YFinanceProvider(ticker_factory=lambda sym: FakeTicker(frame))

    hist = provider.history("PETR4", date(2024, 1, 2), date(2024, 1, 4))
    assert [dc.date for dc in hist] == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    assert hist[1].close == Decimal("11.50")


def test_yfinance_symbol_gets_sa_suffix():
    captured = {}

    def factory(sym):
        captured["sym"] = sym
        idx = pd.to_datetime(["2024-01-02"])
        return FakeTicker(pd.DataFrame({"Close": [9.0]}, index=idx))

    provider = YFinanceProvider(ticker_factory=factory)
    provider.history("PETR4", date(2024, 1, 1), date(2024, 1, 3))
    assert captured["sym"] == "PETR4.SA"


def test_yfinance_empty_frame_raises():
    provider = YFinanceProvider(
        retries=0, ticker_factory=lambda sym: FakeTicker(pd.DataFrame())
    )
    with pytest.raises(ProviderError):
        provider.history("PETR4", date(2024, 1, 1), date(2024, 1, 4))


# --------------------------------------------------------------------------- #
# Service — latest                                                             #
# --------------------------------------------------------------------------- #


def test_service_latest_falls_back_to_yfinance(db):
    brapi = RecordingProvider("brapi", raises=ProviderError("boom", provider="brapi", status_code=429))
    yf = RecordingProvider(
        "yfinance", latest_map={"PETR4": Quote(Decimal("30.00"), date(2024, 1, 5), "yfinance")}
    )
    svc = QuoteService(db, brapi=brapi, yfinance=yf)

    quotes = svc.latest(["PETR4"])
    assert quotes["PETR4"].source == "yfinance"
    assert brapi.latest_calls  # brapi was tried
    assert yf.latest_calls == [["PETR4"]]
    # Result was cached.
    assert cache.get_latest_cached(db, "PETR4") is not None


def test_service_latest_unknown_ticker_does_not_crash_batch(db):
    brapi = RecordingProvider(
        "brapi", latest_map={"PETR4": Quote(Decimal("30.00"), date(2024, 1, 5), "brapi")}
    )
    yf = RecordingProvider(
        "yfinance", latest_map={"MXRF11": Quote(Decimal("10.20"), date(2024, 1, 5), "yfinance")}
    )
    svc = QuoteService(db, brapi=brapi, yfinance=yf)

    quotes = svc.latest(["PETR4", "MXRF11", "NOPE99"])
    assert set(quotes) == {"PETR4", "MXRF11"}  # NOPE99 simply absent, no crash
    assert quotes["PETR4"].source == "brapi"
    assert quotes["MXRF11"].source == "yfinance"
    # yfinance only asked for what brapi missed.
    assert yf.latest_calls == [["MXRF11", "NOPE99"]]


def test_service_latest_cache_hit_avoids_network(db):
    cache.upsert(db, [CacheRow("PETR4", date.today(), Decimal("40.00"), "brapi")])
    svc = QuoteService(db, brapi=ExplodingProvider(), yfinance=ExplodingProvider())

    quotes = svc.latest(["PETR4"])
    assert quotes["PETR4"].price == Decimal("40.00")
    assert quotes["PETR4"].source == "brapi"


def test_service_refresh_latest_bypasses_cache(db):
    cache.upsert(db, [CacheRow("PETR4", date.today(), Decimal("40.00"), "brapi")])
    brapi = RecordingProvider(
        "brapi", latest_map={"PETR4": Quote(Decimal("41.00"), date.today(), "brapi")}
    )
    svc = QuoteService(db, brapi=brapi, yfinance=ExplodingProvider())

    quotes = svc.refresh_latest(["PETR4"])
    assert quotes["PETR4"].price == Decimal("41.00")
    assert brapi.latest_calls == [["PETR4"]]  # forced through despite fresh cache


# --------------------------------------------------------------------------- #
# Service — history (delta fetch)                                              #
# --------------------------------------------------------------------------- #


def _consecutive_days(anchor, n):
    return [anchor + timedelta(days=i) for i in range(n)]


def test_service_history_delta_fetches_only_missing(db):
    days = _consecutive_days(date.today() - timedelta(days=20), 10)  # D1..D10, recent
    # Pre-cache D1..D5.
    cache.upsert(db, [CacheRow("PETR4", d, Decimal("10.00"), "brapi") for d in days[:5]])

    brapi_rows = [DailyClose(d, Decimal("20.00")) for d in days[5:]]  # D6..D10
    brapi = RecordingProvider("brapi", history_map={"PETR4": brapi_rows})
    svc = QuoteService(db, brapi=brapi, yfinance=ExplodingProvider())

    hist = svc.history("PETR4", days[0], days[9])

    # Full range returned, merging cache + fetched.
    assert [dc.date for dc in hist] == days
    # Provider was asked ONLY for the missing tail range.
    assert brapi.history_calls == [("PETR4", days[5], days[9])]
    # New dates persisted.
    assert cache.get_cached_dates(db, "PETR4", days[0], days[9]) == set(days)

    # Second call: everything cached -> no further provider calls.
    brapi.history_calls.clear()
    again = svc.history("PETR4", days[0], days[9])
    assert [dc.date for dc in again] == days
    assert brapi.history_calls == []


def test_service_history_no_cache_fetches_full_range(db):
    days = _consecutive_days(date.today() - timedelta(days=15), 5)
    brapi = RecordingProvider("brapi", history_map={"PETR4": [DailyClose(d, Decimal("5.00")) for d in days]})
    svc = QuoteService(db, brapi=brapi, yfinance=ExplodingProvider())

    hist = svc.history("PETR4", days[0], days[-1])
    assert [dc.date for dc in hist] == days
    assert brapi.history_calls == [("PETR4", days[0], days[-1])]


def test_service_history_old_range_uses_yfinance(db):
    # Entirely older than brapi's ~1y free window -> yfinance, brapi untouched.
    start = date.today() - timedelta(days=800)
    days = _consecutive_days(start, 4)
    yf = RecordingProvider("yfinance", history_map={"PETR4": [DailyClose(d, Decimal("7.00")) for d in days]})
    svc = QuoteService(db, brapi=ExplodingProvider(), yfinance=yf)

    hist = svc.history("PETR4", days[0], days[-1])
    assert [dc.date for dc in hist] == days
    assert yf.history_calls == [("PETR4", days[0], days[-1])]
    # Cached with the yfinance source.
    latest = cache.get_latest_cached(db, "PETR4")
    assert latest.source == "yfinance"


def test_service_history_recent_falls_back_to_yfinance(db):
    days = _consecutive_days(date.today() - timedelta(days=10), 3)
    brapi = RecordingProvider("brapi", raises=ProviderError("down", provider="brapi"))
    yf = RecordingProvider("yfinance", history_map={"PETR4": [DailyClose(d, Decimal("8.00")) for d in days]})
    svc = QuoteService(db, brapi=brapi, yfinance=yf)

    hist = svc.history("PETR4", days[0], days[-1])
    assert [dc.date for dc in hist] == days
    assert brapi.history_calls  # tried brapi
    assert yf.history_calls == [("PETR4", days[0], days[-1])]


def test_service_history_empty_range_returns_empty(db):
    svc = QuoteService(db, brapi=ExplodingProvider(), yfinance=ExplodingProvider())
    assert svc.history("PETR4", date(2024, 1, 5), date(2024, 1, 1)) == []


# --------------------------------------------------------------------------- #
# Portfolio ticker universe                                                    #
# --------------------------------------------------------------------------- #


def test_get_portfolio_tickers_from_summary(db):
    db.add_all(
        [
            PositionSummary(ticker="PETR4", qty_net=Decimal("100")),
            PositionSummary(ticker="MXRF11", qty_net=Decimal("50")),
            PositionSummary(ticker="SOLD3", qty_net=Decimal("0")),  # not held
            PositionSummary(ticker="ITSA4", qty_net=None),  # unknown net -> keep
        ]
    )
    db.commit()

    assert get_portfolio_tickers(db) == ["ITSA4", "MXRF11", "PETR4"]


def test_get_portfolio_tickers_falls_back_to_transactions(db):
    db.add_all(
        [
            Transaction(
                trade_date=date(2024, 1, 2),
                ticker="PETR4",
                market="a_vista",
                side="buy",
                quantity=Decimal("100"),
                price=Decimal("30.00"),
                value=Decimal("3000.00"),
            ),
            Transaction(
                trade_date=date(2024, 1, 3),
                ticker="ITSA4F",  # fractional -> canonicalized
                market="fracionario",
                side="buy",
                quantity=Decimal("5"),
                price=Decimal("9.00"),
                value=Decimal("45.00"),
            ),
        ]
    )
    db.commit()

    assert get_portfolio_tickers(db) == ["ITSA4", "PETR4"]


# --------------------------------------------------------------------------- #
# Opt-in integration (hits the real brapi API)                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not os.getenv("RUN_BRAPI_INTEGRATION"),
    reason="opt-in: set RUN_BRAPI_INTEGRATION=1 (and BRAPI_TOKEN) to run",
)
def test_brapi_integration_real():
    from app.config import get_settings

    settings = get_settings()
    provider = BrapiProvider(settings.BRAPI_BASE_URL, settings.BRAPI_TOKEN)
    quotes = provider.latest(["PETR4"])
    assert "PETR4" in quotes
    assert quotes["PETR4"].price > 0
