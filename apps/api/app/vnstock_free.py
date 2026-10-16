"""Entitlement-aware access to Vnstock Community surfaces.

This module deliberately exposes a small, named operation catalog instead of
accepting arbitrary SDK method paths.  Vnstock is a client library and the
upstream entitlement can change independently of this application; every
response therefore carries the SDK route/source attributes and a status which
can be ``BLOCKED`` without writing anything to the canonical database.
"""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from app.config import Settings

try:  # Optional dependency; CSV/SSI deployments do not require Vnstock.
    from vnstock import Fundamental as _VnFundamental
    from vnstock import Market as _VnMarket
    from vnstock import Reference as _VnReference
    from vnstock import Retail as _VnRetail
except (ImportError, ModuleNotFoundError):  # pragma: no cover - optional env
    _VnFundamental = None
    _VnMarket = None
    _VnReference = None
    _VnRetail = None


class VnstockFreeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FreeOperation:
    operation: str
    group: str
    description: str
    requires_symbol: bool = False
    tier: str = "Community"
    requires_source: bool = False
    source_kind: str = "reference"


# This is the allow-list supported by the official v5 Community documentation.
# Expanded-only methods are listed separately so the UI can explain why they
# are not called with a free account.
FREE_OPERATIONS: tuple[FreeOperation, ...] = (
    FreeOperation("reference.company_info", "reference", "Company overview", True),
    FreeOperation("reference.company_officers", "reference", "Company officers", True),
    FreeOperation("reference.company_shareholders", "reference", "Company shareholders", True),
    FreeOperation("reference.company_ownership", "reference", "Ownership structure", True),
    FreeOperation("reference.company_subsidiaries", "reference", "Subsidiaries", True),
    FreeOperation("reference.company_affiliate", "reference", "Affiliate companies", True),
    FreeOperation("reference.company_capital_history", "reference", "Capital history", True),
    FreeOperation("reference.company_events", "reference", "Company events", True),
    FreeOperation("reference.company_insider_trading", "reference", "Insider trading", True),
    FreeOperation("reference.equity_list", "reference", "Equity master list"),
    FreeOperation("reference.equity_list_by_exchange", "reference", "Equity list by exchange"),
    FreeOperation("reference.equity_list_by_group", "reference", "Equity list by group"),
    FreeOperation("reference.equity_list_by_industry", "reference", "Equity list by industry"),
    FreeOperation("reference.industry_list", "reference", "Industry list"),
    FreeOperation("reference.industry_sectors", "reference", "Industry sectors"),
    FreeOperation("reference.index_list", "reference", "Index list"),
    FreeOperation("reference.index_groups", "reference", "Index groups"),
    FreeOperation("reference.index_info", "reference", "Index information", True),
    FreeOperation("reference.index_description", "reference", "Index description", True),
    FreeOperation("reference.index_members", "reference", "Index members", True),
    FreeOperation("reference.search_symbol", "reference", "International symbol search", True),
    FreeOperation("reference.etf_list", "reference", "ETF list"),
    FreeOperation("reference.futures_list", "reference", "Futures list"),
    FreeOperation("reference.warrant_list", "reference", "Warrant list"),
    FreeOperation("reference.bond_list", "reference", "Bond list"),
    FreeOperation("reference.events_calendar", "reference", "Economic/company events calendar"),
    FreeOperation("reference.events_market", "reference", "Market events"),
    FreeOperation("reference.market_status", "reference", "Market status"),
    FreeOperation("market.equity_quote", "market", "Equity quote", True),
    FreeOperation("market.equity_ohlcv", "market", "Equity OHLCV", True),
    FreeOperation("market.equity_trades", "market", "Equity trades", True),
    FreeOperation("market.index_ohlcv", "market", "Index OHLCV", True),
    FreeOperation("market.futures_quote", "market", "Futures quote", True),
    FreeOperation("market.futures_ohlcv", "market", "Futures OHLCV", True),
    FreeOperation("market.futures_trades", "market", "Futures trades", True),
    FreeOperation("market.warrant_quote", "market", "Warrant quote", True),
    FreeOperation("market.warrant_ohlcv", "market", "Warrant OHLCV", True),
    FreeOperation("market.warrant_trades", "market", "Warrant trades", True),
    FreeOperation("market.etf_quote", "market", "ETF quote", True),
    FreeOperation("market.etf_ohlcv", "market", "ETF OHLCV", True),
    FreeOperation("market.etf_trades", "market", "ETF trades", True),
    FreeOperation("market.bond_quote", "market", "Bond quote", True),
    FreeOperation("market.bond_ohlcv", "market", "Bond OHLCV", True),
    FreeOperation("market.bond_trades", "market", "Bond trades", True),
    FreeOperation("market.multi_quote", "market", "Multi-symbol quote", True),
    FreeOperation("market.crypto_ohlcv", "market", "Crypto OHLCV", True),
    FreeOperation("market.forex_ohlcv", "market", "Forex OHLCV", True),
    FreeOperation("market.commodity_ohlcv", "market", "Commodity OHLCV", True),
    FreeOperation("market.global_index_ohlcv", "market", "Global index OHLCV", True),
    FreeOperation("fundamental.income_statement", "fundamental", "Income statement", True),
    FreeOperation("fundamental.balance_sheet", "fundamental", "Balance sheet", True),
    FreeOperation("fundamental.cash_flow", "fundamental", "Cash-flow statement", True),
    FreeOperation("retail.exchange_rate", "retail", "Vietcombank exchange rates"),
)

EXPANDED_OPERATIONS: tuple[FreeOperation, ...] = (
    FreeOperation("reference.futures_info", "reference", "Single futures contract information", tier="Expanded", requires_symbol=True),
    FreeOperation("reference.warrant_info", "reference", "Single warrant information", tier="Expanded", requires_symbol=True),
    FreeOperation("reference.bond_info", "reference", "Single bond information", tier="Expanded", requires_symbol=True),
    FreeOperation("market.order_book", "market", "Order book", tier="Expanded", requires_symbol=True),
    FreeOperation("market.foreign_flow", "market", "Foreign flow", tier="Expanded", requires_symbol=True),
    FreeOperation("market.proprietary_flow", "market", "Proprietary flow", tier="Expanded", requires_symbol=True),
    FreeOperation("insights.ranking", "insights", "Market ranking", tier="Expanded"),
    FreeOperation("insights.sentiment", "insights", "Market sentiment", tier="Expanded"),
    FreeOperation("insights.flow", "insights", "Market flow", tier="Expanded"),
    FreeOperation("analytics.valuation", "analytics", "Valuation analytics", tier="Expanded", requires_symbol=True),
    FreeOperation("macro.indicator", "macro", "Macro indicator", tier="Bronze+"),
    FreeOperation("fundamental.ratio", "fundamental", "Financial ratios", tier="Expanded", requires_symbol=True),
    FreeOperation("fundamental.note", "fundamental", "Financial statement notes", tier="Expanded", requires_symbol=True),
    FreeOperation("fundamental.financial_health", "fundamental", "Financial health scorecard", tier="Expanded", requires_symbol=True),
    FreeOperation("fundamental.annual_plan", "fundamental", "Annual business plan", tier="Expanded", requires_symbol=True),
)

_OPERATIONS = {item.operation: item for item in (*FREE_OPERATIONS, *EXPANDED_OPERATIONS)}


def operation_catalog() -> list[dict[str, Any]]:
    return [
        {
            "operation": item.operation,
            "group": item.group,
            "description": item.description,
            "tier": item.tier,
            "requires_symbol": item.requires_symbol,
            "status": "available" if item.tier == "Community" else "blocked_without_entitlement",
        }
        for item in _OPERATIONS.values()
    ]


def source_catalog() -> list[dict[str, Any]]:
    """Document the free upstream routes without claiming live health."""
    return [
        {
            "source": "vci",
            "provider": "Viet Capital / VCI route via Vnstock",
            "supported_groups": ["reference", "market", "fundamental"],
            "authentication": "Guest or Community within Vnstock policy",
            "entitlement": "Free for documented Community routes",
            "notes": "Domestic equity, reference and three financial statements; delayed/upstream terms apply.",
        },
        {
            "source": "kbs",
            "provider": "KBS route via Vnstock",
            "supported_groups": ["reference", "market", "fundamental"],
            "authentication": "Guest or Community within Vnstock policy",
            "entitlement": "Free for documented Community routes",
            "notes": "Domestic market/reference and three financial statements; source values can differ from vci.",
        },
        {
            "source": "builtin",
            "provider": "Vnstock local built-in tables",
            "supported_groups": ["reference"],
            "authentication": "None",
            "entitlement": "Free",
            "notes": "Index metadata, market calendar and local session status; no upstream request.",
        },
        {
            "source": "binance",
            "provider": "Binance route via Vnstock",
            "supported_groups": ["market"],
            "authentication": "Public upstream route as governed by Vnstock",
            "entitlement": "Free for documented crypto OHLCV",
            "notes": "Crypto only; not Vietnamese securities data.",
        },
        {
            "source": "dukascopy",
            "provider": "Dukascopy route via Vnstock",
            "supported_groups": ["market"],
            "authentication": "Public upstream route as governed by Vnstock",
            "entitlement": "Free for documented forex/commodity/global-index OHLCV",
            "notes": "International assets only; not a substitute for domestic market data.",
        },
        {
            "source": "vcb",
            "provider": "Vietcombank route via Vnstock Retail",
            "supported_groups": ["retail"],
            "authentication": "Public upstream route as governed by Vnstock",
            "entitlement": "Free for daily exchange-rate table",
            "notes": "Retail().exchange_rate() only; no domestic stock prices.",
        },
    ]


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy/date values without leaking NaN into JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _records(frame: Any, limit: int) -> tuple[list[str], list[dict[str, Any]]]:
    if frame is None:
        return [], []
    if hasattr(frame, "to_dict"):
        try:
            rows = frame.to_dict(orient="records")
        except TypeError:
            rows = frame.to_dict("records")
    elif isinstance(frame, dict):
        rows = [frame]
    elif isinstance(frame, list):
        rows = frame
    else:
        rows = []
    rows = [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in rows[:limit]
        if isinstance(row, dict)
    ]
    if not rows and isinstance(frame, (str, int, float, bool)):
        return ["value"], [{"value": _json_value(frame)}]
    columns = list(rows[0]) if rows else []
    return columns, rows


def _attrs(frame: Any, fallback_source: str | None) -> tuple[str | None, str | None]:
    attrs = getattr(frame, "attrs", {}) or {}
    return attrs.get("source") or fallback_source, attrs.get("route")


def _call_with_supported(method: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    """Call SDK methods across minor v5 signature differences.

    Filtering against the bound method signature prevents an unsupported query
    option from causing a second request with all options silently discarded.
    """
    clean = {key: value for key, value in kwargs.items() if value is not None}
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return method(**clean)
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return method(**clean)
    supported = {key: value for key, value in clean.items() if key in parameters}
    return method(**supported)


def _source(settings: Settings, group: str, operation: str | None = None) -> str | None:
    if group == "market":
        if operation and operation.startswith("market.crypto_"):
            return "binance"
        if operation and operation.startswith(
            ("market.forex_", "market.commodity_", "market.global_index_")
        ):
            return "dukascopy"
        return settings.vnstock_market_source or None
    if group == "retail":
        return "vcb"
    if group in {"reference", "fundamental"}:
        if operation and operation in {
            "reference.index_list",
            "reference.index_info",
            "reference.index_description",
            "reference.index_groups",
            "reference.events_market",
            "reference.market_status",
        }:
            return "builtin"
        return settings.vnstock_reference_source or None
    return None


def _client_for(item: FreeOperation, symbol: str | None) -> tuple[Any, Any]:
    if item.group == "reference":
        if _VnReference is None:
            raise RuntimeError("Vnstock SDK is not installed")
        reference = _VnReference()
        if item.operation.startswith("reference.company_"):
            if not symbol:
                raise ValueError("symbol is required")
            return reference.company(symbol), None
        if item.operation in {
            "reference.index_info",
            "reference.index_description",
            "reference.index_members",
        }:
            if not symbol:
                raise ValueError("symbol is required")
            return reference.index(symbol), None
        return reference, None
    if item.group == "fundamental":
        if _VnFundamental is None:
            raise RuntimeError("Vnstock SDK is not installed")
        if not symbol:
            raise ValueError("symbol is required")
        return _VnFundamental().equity(symbol), None
    if item.group == "retail":
        if _VnRetail is None:
            raise RuntimeError("Vnstock SDK is not installed")
        return _VnRetail(), None
    if _VnMarket is None:
        raise RuntimeError("Vnstock SDK is not installed")
    market = _VnMarket()
    if item.operation == "market.multi_quote":
        return market, None
    if not symbol:
        raise ValueError("symbol is required")
    kind = item.operation.split(".", 2)[1].replace("_quote", "").replace("_ohlcv", "").replace("_trades", "")
    if kind == "global_index":
        return market.index(symbol, scope="global"), None
    return getattr(market, kind)(symbol), None


def _invoke(item: FreeOperation, symbol: str | None, source: str | None, limit: int, period: str, kwargs: dict[str, Any]) -> Any:
    client, _ = _client_for(item, symbol)
    op = item.operation
    if op.startswith("reference."):
        name = op.removeprefix("reference.")
        if name.startswith("company_"):
            target = getattr(client, name.removeprefix("company_"))
            return _call_with_supported(target, {"symbol": symbol, "source": source})
        if name.startswith("equity_"):
            target = getattr(client.equity, name.removeprefix("equity_"))
            return _call_with_supported(target, {"source": source, **kwargs})
        if name.startswith("industry_"):
            target = getattr(client.industry, name.removeprefix("industry_"))
            return _call_with_supported(target, {"source": source, **kwargs})
        if name.startswith("index_"):
            suffix = name.removeprefix("index_")
            target = (
                getattr(client, suffix)
                if name in {"index_info", "index_description", "index_members"}
                else getattr(client.index, suffix)
            )
            return _call_with_supported(target, {"symbol": symbol, "source": source, **kwargs})
        if name == "search_symbol":
            return _call_with_supported(client.search.symbol, {"query": symbol})
        if name == "market_status":
            return _call_with_supported(client.market.status, kwargs)
        if name in {"etf_list", "futures_list", "warrant_list", "bond_list"}:
            namespace = name.removesuffix("_list")
            target = getattr(client, namespace).list
            return _call_with_supported(target, {"source": source, **kwargs})
        namespace, method_name = name.split("_", 1)
        target = getattr(getattr(client, namespace), method_name)
        return _call_with_supported(target, {"source": source, **kwargs})
    if op.startswith("fundamental."):
        method = getattr(client, op.removeprefix("fundamental."))
        return _call_with_supported(method, {"period": period, "source": source, **kwargs})
    if op == "retail.exchange_rate":
        return _call_with_supported(client.exchange_rate, kwargs)
    method_name = op.removeprefix("market.")
    if op == "market.multi_quote":
        symbols = [part.strip().upper() for part in (symbol or "").split(",") if part.strip()]
        return _call_with_supported(client.quote, {"symbols": symbols, "source": source})
    method = getattr(
        client,
        method_name.removeprefix("equity_")
        .removeprefix("index_")
        .removeprefix("futures_")
        .removeprefix("warrant_")
        .removeprefix("etf_")
        .removeprefix("bond_")
        .removeprefix("crypto_")
        .removeprefix("forex_")
        .removeprefix("commodity_")
        .removeprefix("global_index_"),
    )
    method_args = {"source": source, **kwargs}
    if method_name.endswith("_trades"):
        method_args["limit"] = limit
    elif method_name.endswith("_ohlcv"):
        method_args.update({"length": limit, "interval": kwargs.get("interval") or "1D"})
    return _call_with_supported(method, method_args)


async def fetch_free_operation(
    operation: str,
    *,
    settings: Settings,
    symbol: str | None = None,
    source: str | None = None,
    limit: int = 100,
    period: str = "year",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _OPERATIONS.get(operation)
    if item is None:
        return {"status": VnstockFreeStatus.FAILED, "error_code": "UNKNOWN_OPERATION", "operation": operation}
    if item.tier != "Community":
        return {
            "status": VnstockFreeStatus.BLOCKED,
            "error_code": "ENTITLEMENT_REQUIRED",
            "operation": operation,
            "tier_required": item.tier,
            "message": "Official Vnstock documentation marks this route as non-Community.",
        }
    if item.requires_symbol and not symbol:
        return {"status": VnstockFreeStatus.FAILED, "error_code": "SYMBOL_REQUIRED", "operation": operation}
    # Reference lists can legitimately exceed 500 rows (the current HOSE
    # universe is ~400 symbols). Keep a defensive upper bound while allowing
    # an operator's read-only reconciliation to receive the complete list.
    bounded_limit = max(1, min(limit, 5_000))
    selected_source = source or _source(settings, item.group, operation)
    allowed_sources = {"vci", "kbs"}
    if item.group == "retail":
        allowed_sources = {"vcb"}
    elif operation.startswith("market.crypto_"):
        allowed_sources = {"binance"}
    elif operation.startswith(
        ("market.forex_", "market.commodity_", "market.global_index_")
    ):
        allowed_sources = {"dukascopy"}
    elif selected_source == "builtin":
        allowed_sources = {"builtin"}
    if selected_source and selected_source.lower() not in allowed_sources:
        return {
            "status": VnstockFreeStatus.BLOCKED,
            "error_code": "SOURCE_NOT_AVAILABLE_ON_COMMUNITY",
            "operation": operation,
            "group": item.group,
            "symbol": symbol,
            "entitlement_tier": item.tier,
            "message": f"This Community route is limited to the documented sources: {', '.join(sorted(allowed_sources))}.",
        }
    retrieved_at = datetime.now(UTC)
    try:
        frame = await asyncio.to_thread(
            _invoke, item, symbol, selected_source, bounded_limit, period, extra or {}
        )
        columns, rows = _records(frame, bounded_limit)
        source_name, route = _attrs(frame, selected_source)
        return {
            "status": VnstockFreeStatus.SUCCESS if rows else VnstockFreeStatus.BLOCKED,
            "operation": operation,
            "group": item.group,
            "symbol": symbol,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "source": source_name,
            "route": route,
            "retrieved_at": retrieved_at,
            "entitlement_tier": item.tier,
            "provenance": {
                "provider_id": "vnstock",
                "sdk": "vnstock-v5",
                "source": source_name,
                "route": route,
                "mode": "live",
                "persisted": False,
                "notes": "Read-only response; canonical database persistence requires a typed importer and unit validation.",
            },
            "message": None if rows else "No rows returned; entitlement/source/schema must be checked.",
        }
    except Exception as exc:  # noqa: BLE001
        # Provider-specific exceptions are intentionally handled at this boundary
        # so credentials and raw upstream payloads never enter API responses.
        name = type(exc).__name__.lower()
        blocked = any(token in name for token in ("entitlement", "ratelimit", "forbidden", "unauthor"))
        return {
            "status": VnstockFreeStatus.BLOCKED if blocked else VnstockFreeStatus.FAILED,
            "error_code": "ENTITLEMENT_REQUIRED" if blocked else "UPSTREAM_ERROR",
            "operation": operation,
            "group": item.group,
            "symbol": symbol,
            "retrieved_at": retrieved_at,
            "entitlement_tier": item.tier,
            "message": "Vnstock request was blocked by entitlement/quota." if blocked else "Vnstock request failed; inspect provider health logs.",
        }

