"""Read-only financial statement adapter for the Vnstock v5 Community routes.

The canonical financial repository remains the source of truth for imported and
validated statements.  This adapter is deliberately read-only: it lets the
analysis page show an entitled Vnstock response when no canonical rows exist,
without silently promoting that response to verified production data.
"""

from __future__ import annotations

import asyncio
import calendar
import math
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from app.analytics.fundamental import calculate_financial_metrics
from app.config import Settings
from app.schemas import (
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementItem,
    FinancialStatementPeriod,
    FinancialStatementsResponse,
    FinancialTrendResponse,
)
from app.vnstock_free import fetch_free_operation

SOURCE_URL = "https://vnstocks.com/docs/vnstock/tham-chieu-reference"
SOURCE_NAME = "Vnstock v5 (Vnstock upstream)"
READ_ONLY_WARNING = (
    "Dữ liệu đọc trực tiếp từ Vnstock Community, chưa lưu vào canonical database "
    "và chưa được hệ thống xác minh độc lập. Phạm vi hợp nhất/riêng lẻ theo mặc "
    "định của provider; kỳ kết thúc được suy ra từ nhãn kỳ báo cáo."
)

# Vnstock VAS ids -> the canonical item codes consumed by the financial engine.
_ITEM_MAP: dict[str, tuple[str, str]] = {
    "IS_NET_REVENUE": ("revenue", "income"),
    "IS_REVENUE": ("revenue", "income"),
    "IS_GROSS_PROFIT": ("gross_profit", "income"),
    "IS_OPERATING_PROFIT": ("operating_income", "income"),
    "IS_PROFIT_BEFORE_TAX": ("profit_before_tax", "income"),
    "IS_CORPORATE_INCOME_TAX_EXPENSES": ("tax_expense", "income"),
    "IS_NET_PROFIT_AFTER_TAX": ("net_income", "income"),
    "IS_PROFIT_AFTER_TAX_FOR_SHAREHOLDERS_OF_PARENT_COMPANY": (
        "net_income_attributable_to_parent",
        "income",
    ),
    "BS_SHORT_TERM_ASSETS": ("current_assets", "balance"),
    "BS_CASH_AND_PRECIOUS_METALS": ("cash_and_equivalents", "balance"),
    "BS_INVENTORIES": ("inventory", "balance"),
    "BS_SHORT_TERM_LIABILITIES": ("current_liabilities", "balance"),
    "BS_TOTAL_ASSETS": ("total_assets", "balance"),
    "BS_TOTAL_LIABILITIES": ("total_liabilities", "balance"),
    "BS_EQUITY": ("total_equity", "balance"),
    "BS_OWNERS_EQUITY": ("total_equity", "balance"),
    "CF_NET_CASH_FLOWS_FROM_OPERATING_ACTIVITIES": (
        "operating_cash_flow",
        "cash_flow",
    ),
    "CF_NET_CASH_FLOWS_FROM_INVESTING_ACTIVITIES": (
        "investing_cash_flow",
        "cash_flow",
    ),
    "CF_NET_CASH_FLOWS_FROM_FINANCING_ACTIVITIES": (
        "financing_cash_flow",
        "cash_flow",
    ),
}


def _period_label(value: Any) -> tuple[str, int, int | None, datetime]:
    """Return period type/year/quarter and a deterministic display timestamp."""

    text = str(value).strip()
    if "-Q" in text:
        year_text, quarter_text = text.split("-Q", 1)
        year, quarter = int(year_text), int(quarter_text)
        month = quarter * 3
        end = date(year, month, calendar.monthrange(year, month)[1])
        return "quarter", year, quarter, datetime(end.year, end.month, end.day, tzinfo=UTC)
    year = int(text[:4])
    end = date(year, 12, 31)
    return "year", year, None, datetime(end.year, end.month, end.day, tzinfo=UTC)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _unit(value: Any) -> str:
    text = str(value or "VND").strip().upper()
    return "VND" if text in {"VNĐ", "VND", "₫"} else text


def _fetch(operation: str, symbol: str, period: str, limit: int, settings: Settings) -> dict[str, Any]:
    return asyncio.run(
        fetch_free_operation(
            operation,
            settings=settings,
            symbol=symbol,
            period=period,
            limit=limit,
        )
    )


def _raw_groups(
    symbol: str,
    period: str,
    limit: int,
    settings: Settings,
) -> tuple[dict[str, dict[str, dict[str, Any]]], list[dict[str, Any]], str | None]:
    groups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    responses = []
    errors: list[str] = []
    for statement_type, operation in (
        ("income", "fundamental.income_statement"),
        ("balance", "fundamental.balance_sheet"),
        ("cash_flow", "fundamental.cash_flow"),
    ):
        response = _fetch(operation, symbol, period, limit, settings)
        responses.append(response)
        if response.get("status") != "SUCCESS":
            errors.append(f"{statement_type}: {response.get('message') or response.get('error_code') or 'unavailable'}")
            continue
        for row in response.get("rows", []):
            label = str(row.get("period") or "").strip()
            item_id = str(row.get("id") or "").strip()
            if not label or not item_id or _as_float(row.get("value")) is None:
                continue
            # One response can contain multiple provider variants of a row. Keep
            # the first stable row for a period/id and never invent a replacement.
            groups[label].setdefault(item_id, {**row, "statement_type": statement_type})
    source = next((item.get("source") for item in responses if item.get("source")), None)
    if errors and not groups:
        raise LookupError("; ".join(errors))
    return groups, responses, source


def _periods_from_groups(
    symbol: str,
    groups: dict[str, dict[str, dict[str, Any]]],
    responses: list[dict[str, Any]],
    source: str | None,
    *,
    limit: int,
) -> list[FinancialStatementPeriod]:
    retrieved_at = next((item.get("retrieved_at") for item in responses if item.get("retrieved_at")), None)
    if isinstance(retrieved_at, str):
        retrieved_at = datetime.fromisoformat(retrieved_at)
    if not isinstance(retrieved_at, datetime):
        retrieved_at = datetime.now(UTC)
    periods: list[FinancialStatementPeriod] = []
    for label in sorted(groups, reverse=True)[:limit]:
        period_type, year, quarter, period_end = _period_label(label)
        items: list[FinancialStatementItem] = []
        chosen: set[str] = set()
        rows = sorted(
            groups[label].items(),
            key=lambda pair: (
                0
                if pair[0] == "IS_NET_REVENUE"
                else 1
                if pair[0] == "IS_REVENUE"
                else 0
            ),
        )
        for raw_id, row in rows:
            mapping = _ITEM_MAP.get(raw_id)
            if mapping is None:
                continue
            item_code, statement_type = mapping
            # Prefer net revenue and parent-attributable profit over their gross
            # fallback rows when both are present.
            if item_code in chosen:
                continue
            chosen.add(item_code)
            value = _as_float(row.get("value"))
            if value is None:
                continue
            items.append(
                FinancialStatementItem(
                    statement_type=statement_type,
                    item_code=item_code,
                    raw_item_code=raw_id,
                    value=value,
                    unit=_unit(row.get("unit")),
                    raw_value=value,
                    raw_unit=str(row.get("unit") or "VND"),
                    source_name=f"{SOURCE_NAME} · {source or 'unknown source'}",
                    source_url=SOURCE_URL,
                    verification_status="unverified",
                    updated_at=retrieved_at,
                )
            )
        periods.append(
            FinancialStatementPeriod(
                period_end=period_end,
                period_type=period_type,
                fiscal_year=year,
                fiscal_quarter=quarter,
                statement_scope="consolidated",
                statement_status="original",
                accounting_standard="VAS (provider response)",
                currency="VND",
                source_name=f"{SOURCE_NAME} · {source or 'unknown source'}",
                source_url=SOURCE_URL,
                verification_status="unverified",
                retrieved_at=retrieved_at,
                updated_at=retrieved_at,
                items=items,
            )
        )
    return periods


def fetch_live_statements(
    symbol: str,
    *,
    period: str = "quarter",
    limit: int = 8,
    settings: Settings,
) -> FinancialStatementsResponse:
    symbol = symbol.strip().upper()
    groups, responses, source = _raw_groups(symbol, period, max(limit * 30, 100), settings)
    periods = _periods_from_groups(symbol, groups, responses, source, limit=limit)
    if not periods:
        raise LookupError(f"Vnstock chưa trả BCTC cho {symbol}.")
    return FinancialStatementsResponse(
        symbol=symbol,
        automatic_sync_status="live",
        automatic_sync_message=(
            f"Đang hiển thị {len(periods)} kỳ BCTC live từ Vnstock; "
            "chưa ghi vào canonical database. " + READ_ONLY_WARNING
        ),
        periods=periods,
    )


def _values(period: FinancialStatementPeriod) -> dict[str, float]:
    return {item.item_code: item.value for item in period.items}


def _inputs(current: dict[str, float], previous: dict[str, float] | None, sequential: dict[str, float] | None, *, period_type: str) -> FinancialInputs:
    previous = previous or {}
    sequential = sequential or {}
    return FinancialInputs(
        revenue=current.get("revenue"),
        prior_revenue=previous.get("revenue"),
        previous_period_revenue=sequential.get("revenue"),
        net_income=current.get("net_income"),
        net_income_attributable_to_parent=current.get("net_income_attributable_to_parent"),
        prior_net_income=previous.get("net_income"),
        previous_period_net_income=sequential.get("net_income"),
        period_months=3 if period_type == "quarter" else 12,
        total_assets=current.get("total_assets"),
        prior_total_assets=previous.get("total_assets"),
        total_equity=current.get("total_equity"),
        prior_total_equity=previous.get("total_equity"),
        total_debt=current.get("total_debt") or current.get("total_liabilities"),
        prior_total_debt=previous.get("total_debt") or previous.get("total_liabilities"),
        cash_and_equivalents=current.get("cash_and_equivalents"),
        prior_cash_and_equivalents=previous.get("cash_and_equivalents"),
        current_assets=current.get("current_assets"),
        inventory=current.get("inventory"),
        current_liabilities=current.get("current_liabilities"),
        operating_income=current.get("operating_income"),
        profit_before_tax=current.get("profit_before_tax"),
        tax_expense=current.get("tax_expense"),
        gross_profit=current.get("gross_profit"),
        operating_cash_flow=current.get("operating_cash_flow"),
    )


def fetch_live_metrics(symbol: str, *, period: str = "quarter", limit: int = 8, settings: Settings) -> FinancialMetricResult:
    statements = fetch_live_statements(symbol, period=period, limit=limit, settings=settings)
    current = statements.periods[0]
    sequential = statements.periods[1] if len(statements.periods) > 1 else None
    previous = next(
        (
            item
            for item in statements.periods[1:]
            if item.fiscal_year == current.fiscal_year - 1
            and item.fiscal_quarter == current.fiscal_quarter
        ),
        sequential,
    )
    result = calculate_financial_metrics(
        _inputs(
            _values(current),
            _values(previous) if previous else None,
            _values(sequential) if sequential else None,
            period_type=current.period_type,
        )
    )
    return result.model_copy(
        update={
            "symbol": statements.symbol,
            "period_type": current.period_type,
            "period_end": current.period_end,
            "source_name": current.source_name,
            "statement_scope": current.statement_scope,
            "statement_status": current.statement_status,
            "warnings": [READ_ONLY_WARNING, *result.warnings],
            "metric_metadata": {
                code: metadata.model_copy(update={"as_of_date": current.period_end})
                for code, metadata in result.metric_metadata.items()
            },
        }
    )


def fetch_live_history(symbol: str, *, period_type: str = "year", limit: int = 8, settings: Settings) -> FinancialTrendResponse:
    statements = fetch_live_statements(symbol, period=period_type, limit=limit, settings=settings)
    results: list[FinancialMetricResult] = []
    for index, period in enumerate(reversed(statements.periods)):
        previous = statements.periods[len(statements.periods) - index - 2] if index + 1 < len(statements.periods) else None
        calculated = calculate_financial_metrics(
            _inputs(_values(period), _values(previous) if previous else None, _values(previous) if previous else None, period_type=period.period_type)
        )
        results.append(
            calculated.model_copy(
                update={
                    "symbol": statements.symbol,
                    "period_type": period.period_type,
                    "period_end": period.period_end,
                    "source_name": period.source_name,
                    "statement_scope": period.statement_scope,
                    "statement_status": period.statement_status,
                    "warnings": [READ_ONLY_WARNING, *calculated.warnings],
                    "metric_metadata": {
                        code: metadata.model_copy(update={"as_of_date": period.period_end})
                        for code, metadata in calculated.metric_metadata.items()
                    },
                }
            )
        )
    return FinancialTrendResponse(
        symbol=statements.symbol,
        period_type=period_type,
        statement_scope="consolidated",
        periods=list(reversed(results)),
        warnings=[READ_ONLY_WARNING],
    )
