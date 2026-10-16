from datetime import UTC, datetime

import app.vnstock_financials as live
from app.config import Settings


def _response(operation: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "SUCCESS",
        "operation": operation,
        "rows": rows,
        "source": "vci",
        "retrieved_at": datetime(2026, 10, 16, tzinfo=UTC).isoformat(),
    }


def test_live_statements_map_vnstock_rows_without_promoting_them(monkeypatch):
    rows = {
        "fundamental.income_statement": [
            {"period": "2026-Q2", "id": "IS_REVENUE", "unit": "VNĐ", "value": 10},
            {"period": "2026-Q2", "id": "IS_NET_REVENUE", "unit": "VNĐ", "value": 9},
            {"period": "2026-Q2", "id": "IS_GROSS_PROFIT", "unit": "VNĐ", "value": 3},
            {"period": "2026-Q2", "id": "IS_NET_PROFIT_AFTER_TAX", "unit": "VNĐ", "value": 2},
        ],
        "fundamental.balance_sheet": [
            {"period": "2026-Q2", "id": "BS_TOTAL_ASSETS", "unit": "VNĐ", "value": 100},
            {"period": "2026-Q2", "id": "BS_EQUITY", "unit": "VNĐ", "value": 50},
        ],
        "fundamental.cash_flow": [
            {
                "period": "2026-Q2",
                "id": "CF_NET_CASH_FLOWS_FROM_OPERATING_ACTIVITIES",
                "unit": "VNĐ",
                "value": 4,
            }
        ],
    }

    monkeypatch.setattr(
        live,
        "_fetch",
        lambda operation, symbol, period, limit, settings: _response(operation, rows[operation]),
    )

    result = live.fetch_live_statements("HPG", settings=Settings(), limit=4)

    assert result.automatic_sync_status == "live"
    assert result.periods[0].verification_status == "unverified"
    assert result.periods[0].source_name.endswith("· vci")
    assert result.periods[0].period_end.isoformat().startswith("2026-06-30")
    mapped = {item.item_code: item for item in result.periods[0].items}
    assert mapped["revenue"].value == 9  # net revenue wins over gross revenue
    assert mapped["operating_cash_flow"].value == 4
    assert result.periods[0].items[0].source_url == live.SOURCE_URL


def test_live_metrics_uses_same_quarter_for_yoy(monkeypatch):
    def statement_rows(statement_type: str) -> list[dict[str, object]]:
        values = {
            "2026-Q2": 120,
            "2026-Q1": 90,
            "2025-Q2": 100,
        }
        rows = []
        for period, revenue in values.items():
            rows.extend(
                [
                    {"period": period, "id": "IS_NET_REVENUE", "unit": "VNĐ", "value": revenue},
                    {"period": period, "id": "IS_NET_PROFIT_AFTER_TAX", "unit": "VNĐ", "value": revenue / 10},
                    {"period": period, "id": "BS_TOTAL_ASSETS", "unit": "VNĐ", "value": 1000},
                    {"period": period, "id": "BS_EQUITY", "unit": "VNĐ", "value": 500},
                ]
            )
        return rows

    monkeypatch.setattr(
        live,
        "_fetch",
        lambda operation, symbol, period, limit, settings: _response(
            operation,
            statement_rows(operation),
        ),
    )

    result = live.fetch_live_metrics("HPG", settings=Settings(), limit=8)

    assert result.metrics["revenue_yoy_percent"] == 20.0
    assert result.metrics["revenue_qoq_percent"] == 33.333333
    assert result.symbol == "HPG"
    assert any("chưa lưu vào canonical database" in warning for warning in result.warnings)
