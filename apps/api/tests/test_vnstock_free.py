import asyncio
from datetime import datetime
from typing import ClassVar

import app.vnstock_free as free
from app.config import Settings


class Frame:
    attrs: ClassVar = {"source": "vci", "route": "reference/equity/list"}

    def to_dict(self, orient="records"):
        assert orient == "records"
        return [{"symbol": "HPG", "as_of": datetime(2026, 10, 16), "missing": float("nan")}]


class Ref:
    class Equity:
        def list(self, **kwargs):
            assert kwargs["source"] == "vci"
            return Frame()

    def __init__(self):
        self.equity = self.Equity()


class Fundamental:
    class Equity:
        def income_statement(self, **kwargs):
            assert kwargs["period"] == "quarter"
            return Frame()

    def equity(self, symbol):
        assert symbol == "HPG"
        return self.Equity()


class Retail:
    def exchange_rate(self, date=""):
        assert date == "2026-10-16"
        return Frame()


def test_catalog_separates_community_and_expanded_operations():
    catalog = free.operation_catalog()
    assert any(row["operation"] == "fundamental.income_statement" and row["tier"] == "Community" for row in catalog)
    assert any(row["operation"] == "insights.ranking" and row["status"] == "blocked_without_entitlement" for row in catalog)
    assert {row["source"] for row in free.source_catalog()} == {
        "vci", "kbs", "builtin", "binance", "dukascopy", "vcb"
    }


def test_catalog_covers_documented_free_aliases_and_source_policies():
    catalog = {row["operation"]: row for row in free.operation_catalog()}
    assert catalog["reference.company_overview"]["sdk_route"] == "fundamental.company.overview"
    assert catalog["reference.search_info"]["default_source"] == "dukascopy"
    assert catalog["reference.index_list"]["default_source"] == "builtin"
    assert catalog["reference.index_members"]["requires_group"] is True
    assert catalog["market.futures_quote"]["allowed_sources"] == ["kbs"]


def test_expanded_route_is_blocked_without_calling_sdk(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Expanded route must not call the SDK")

    monkeypatch.setattr(free, "_VnMarket", fail)
    result = asyncio.run(free.fetch_free_operation("insights.ranking", settings=Settings()))
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "ENTITLEMENT_REQUIRED"


def test_community_rejects_non_permitted_source_without_calling_sdk(monkeypatch):
    monkeypatch.setattr(free, "_VnReference", lambda: (_ for _ in ()).throw(AssertionError()))
    result = asyncio.run(
        free.fetch_free_operation("reference.equity_list", settings=Settings(), source="kbs")
    )
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "SOURCE_NOT_AVAILABLE_ON_COMMUNITY"


def test_reference_response_is_bounded_and_json_safe(monkeypatch):
    monkeypatch.setattr(free, "_VnReference", Ref)
    result = asyncio.run(
        free.fetch_free_operation("reference.equity_list", settings=Settings(), limit=10)
    )
    assert result["status"] == "SUCCESS"
    assert result["rows"][0]["as_of"] == "2026-10-16T00:00:00"
    assert result["rows"][0]["missing"] is None
    assert result["provenance"]["persisted"] is False


def test_fundamental_community_route_preserves_period_and_symbol(monkeypatch):
    monkeypatch.setattr(free, "_VnFundamental", Fundamental)
    result = asyncio.run(
        free.fetch_free_operation(
            "fundamental.income_statement",
            settings=Settings(),
            symbol="HPG",
            period="quarter",
        )
    )
    assert result["status"] == "SUCCESS"
    assert result["symbol"] == "HPG"


def test_retail_exchange_rate_is_free_and_preserves_date(monkeypatch):
    monkeypatch.setattr(free, "_VnRetail", Retail)
    result = asyncio.run(
        free.fetch_free_operation(
            "retail.exchange_rate",
            settings=Settings(),
            extra={"date": "2026-10-16"},
        )
    )
    assert result["status"] == "SUCCESS"
    assert result["source"] == "vci"  # test frame provenance remains explicit
