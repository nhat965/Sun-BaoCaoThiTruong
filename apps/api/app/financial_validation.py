"""Deterministic validation rules for one canonical financial period."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

VALIDATION_VERSION = "financial-validation-v1"
_DB_MAX_ABS = Decimal("1e22")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    item_code: str | None = None
    source_name: str | None = None


@dataclass(frozen=True)
class PeriodValidation:
    checks: list[str]
    issues: list[ValidationIssue]

    @property
    def errors(self) -> list[str]:
        return [issue.message for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[str]:
        return [issue.message for issue in self.issues if issue.severity == "warning"]

    @property
    def status(self) -> str:
        if self.errors:
            return "invalid"
        if any(issue.code == "insufficient_data" for issue in self.issues):
            return "insufficient_data"
        if self.warnings:
            return "warning"
        return "valid"


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    item_code: str | None,
    source_name: str,
) -> ValidationIssue:
    return ValidationIssue(code, severity, message, item_code, source_name)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def validate_period(
    *,
    period_type: str,
    period_start: datetime | None,
    period_end: datetime,
    reported_at: datetime | None,
    currency: str,
    statement_scope: str,
    statement_status: str,
    source_name: str,
    source_url: str | None,
    values: dict[str, Decimal],
) -> PeriodValidation:
    checks = ["schema", "period_identity", "unit_normalization"]
    issues: list[ValidationIssue] = []
    add = lambda code, severity, message, item_code=None: issues.append(
        _issue(
            code,
            severity,
            message,
            item_code=item_code,
            source_name=source_name,
        )
    )

    if not currency or len(currency) != 3 or not currency.isalpha():
        add("invalid_currency", "error", "currency must be a three-letter code")
    if statement_scope not in {"consolidated", "separate"}:
        add("invalid_scope", "error", "statement scope is not supported")
    if statement_status not in {"original", "amended"}:
        add("invalid_statement_status", "error", "statement status is not supported")
    normalized_start = _utc(period_start)
    normalized_end = _utc(period_end)
    normalized_reported_at = _utc(reported_at)
    if normalized_start is not None and normalized_end is not None and normalized_start > normalized_end:
        add("period_order", "error", "period_start must not be after period_end")
    if (
        normalized_reported_at is not None
        and normalized_end is not None
        and normalized_reported_at < normalized_end
    ):
        add(
            "reported_before_period_end",
            "warning",
            "reported_at precedes period_end; verify source metadata",
        )
    if not source_url:
        add("missing_source_url", "warning", "source_url is missing")

    for item_code, value in values.items():
        if not value.is_finite():
            add("non_finite_value", "error", f"{item_code} is not finite", item_code)
        elif abs(value) > _DB_MAX_ABS:
            add("numeric_overflow", "error", f"{item_code} exceeds database numeric range", item_code)

    for item_code in ("total_assets", "total_liabilities", "shares_outstanding"):
        if item_code in values and values[item_code] < 0:
            add("negative_total", "error", f"{item_code} must not be negative", item_code)

    balance_keys = {"total_assets", "total_liabilities", "total_equity"}
    if balance_keys.issubset(values):
        checks.append("balance_sheet_equation")
        assets = values["total_assets"]
        right_side = values["total_liabilities"] + values["total_equity"]
        tolerance = max(Decimal(1), abs(assets) * Decimal("0.001"))
        if abs(assets - right_side) > tolerance:
            add(
                "balance_equation_mismatch",
                "error",
                "total_assets != total_liabilities + total_equity within tolerance",
            )
    else:
        add(
            "insufficient_data",
            "warning",
            "balance equation not checked because required items are missing",
        )

    income_keys = {"revenue", "cost_of_goods_sold", "gross_profit"}
    if income_keys.issubset(values):
        checks.append("income_statement_relationships")
        expected = values["revenue"] - values["cost_of_goods_sold"]
        tolerance = max(Decimal(1), abs(expected) * Decimal("0.001"))
        if abs(expected - values["gross_profit"]) > tolerance:
            add(
                "gross_profit_mismatch",
                "warning",
                "gross_profit does not reconcile to revenue minus cost_of_goods_sold",
                "gross_profit",
            )
    else:
        add(
            "insufficient_data",
            "warning",
            "income statement relationship not checked because required items are missing",
        )

    cash_keys = {"cash_beginning", "cash_ending", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow"}
    if cash_keys.issubset(values):
        checks.append("cash_flow_reconciliation")
        fx_effect = values.get("foreign_exchange_effect", Decimal(0))
        expected = (
            values["cash_beginning"]
            + values["operating_cash_flow"]
            + values["investing_cash_flow"]
            + values["financing_cash_flow"]
            + fx_effect
        )
        tolerance = max(Decimal(1), abs(expected) * Decimal("0.001"))
        if abs(expected - values["cash_ending"]) > tolerance:
            add(
                "cash_flow_mismatch",
                "warning",
                "cash flow totals do not reconcile to ending cash within tolerance",
            )

    return PeriodValidation(checks, issues)
