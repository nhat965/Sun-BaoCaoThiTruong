from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Provenance(BaseModel):
    source: str
    source_url: str | None = None
    provider_symbol: str
    retrieved_at: datetime
    market_timestamp: datetime | None = None
    mode: Literal["live", "fixture"]
    delayed: bool = True
    validation_status: Literal["valid", "partial", "invalid"] = "valid"
    adjustment_policy: str = "unadjusted"
    notes: str | None = None


class Security(BaseModel):
    symbol: str
    name: str
    exchange: str
    currency: str = "VND"
    aliases: list[str] = Field(default_factory=list)
    industry: str | None = None
    sector: str | None = None
    listing_status: Literal["active", "inactive", "delisted", "suspended"] = "active"
    security_type: str = "stock"
    provider_ids: dict[str, str] = Field(default_factory=dict)
    source_name: str | None = None
    source_url: str | None = None
    last_updated: datetime | None = None


class PriceBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceSeries(BaseModel):
    security: Security
    interval: str
    adjusted: bool
    bars: list[PriceBar]
    provenance: Provenance


class IndicatorValue(BaseModel):
    value: float | None
    signal: Literal["positive", "negative", "neutral", "unavailable"]
    explanation: str


class TechnicalSnapshot(BaseModel):
    formula_version: str = "technical-v2"
    calculated_at: datetime
    sample_size: int
    indicators: dict[str, IndicatorValue]
    component_scores: dict[str, float | None] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    publisher: str
    published_at: datetime | None = None
    url: HttpUrl
    related_symbols: list[str]
    relevance_score: float = Field(default=0, ge=0, le=1)
    event_category: str = "other"
    source_credibility: Literal["official", "established_media", "unknown"] = "unknown"
    source_url: str | None = None
    retrieved_at: datetime | None = None
    event_summary: str | None = None
    facts: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    security: Security
    latest_price: float
    previous_close: float | None
    change_percent: float | None
    prices: PriceSeries
    technicals: TechnicalSnapshot
    news: list[NewsItem]
    summary: list[str]
    limitations: list[str]
    generated_at: datetime
    evidence_count: int = Field(ge=0)
    fundamental_status: Literal["available", "partial", "unavailable"] = "unavailable"
    fundamental_message: str = "Chưa có nguồn báo cáo tài chính được xác minh."
    bullish_factors: list[str] = Field(default_factory=list)
    bearish_factors: list[str] = Field(default_factory=list)
    scenarios: dict[str, list[str]] = Field(default_factory=dict)


class SourceStatus(BaseModel):
    name: str
    capabilities: list[str]
    authentication: str
    availability: Literal["available", "configured", "unavailable", "fixture"]
    freshness: str
    licensing: str
    last_checked_at: datetime | None = None
    message: str | None = None


class SourceDiagnostic(SourceStatus):
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0


class DataQualityReport(BaseModel):
    generated_at: datetime
    market_data_mode: Literal["live", "fixture"]
    securities_count: int
    active_securities_count: int
    exchange_distribution: dict[str, int] = Field(default_factory=dict)
    price_observations_count: int
    symbols_with_price_history: int = 0
    symbols_missing_price_history: int = 0
    price_coverage_percent: float = Field(default=0, ge=0, le=100)
    missing_price_symbols: list[str] = Field(default_factory=list)
    price_quality_alerts: dict[str, int] = Field(default_factory=dict)
    latest_market_timestamp_by_exchange: dict[str, datetime | None] = Field(
        default_factory=dict
    )
    last_market_timestamp: datetime | None = None
    last_retrieval_timestamp: datetime | None = None
    sources: list[SourceDiagnostic]
    issues: list[str] = Field(default_factory=list)


class SecuritiesImportResult(BaseModel):
    inserted: int
    updated: int
    rejected: int
    errors: list[str]


class CorporateAction(BaseModel):
    action_type: Literal[
        "stock_split", "cash_dividend", "bonus_share", "rights_issue", "other"
    ]
    effective_at: datetime
    ratio: float | None = None
    cash_amount: float | None = None
    source_name: str
    source_url: str | None = None
    verification_status: Literal["verified", "unverified", "rejected"] = "unverified"
    retrieved_at: datetime


class CorporateActionImportResult(BaseModel):
    inserted: int
    updated: int
    rejected: int
    errors: list[str] = Field(default_factory=list)


class FinancialInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue: float | None = None
    prior_revenue: float | None = None
    net_income: float | None = None
    prior_net_income: float | None = None
    total_assets: float | None = None
    prior_total_assets: float | None = None
    total_equity: float | None = None
    prior_total_equity: float | None = None
    total_debt: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    operating_income: float | None = None
    gross_profit: float | None = None
    interest_expense: float | None = None
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    shares_outstanding: float | None = None
    market_price: float | None = None
    enterprise_value: float | None = None
    ebitda: float | None = None


class FinancialMetricResult(BaseModel):
    metrics: dict[str, float | None]
    calculated_at: datetime
    formula_version: str = "fundamental-v1"
    warnings: list[str]
    symbol: str | None = None
    period_type: str | None = None
    period_end: datetime | None = None
    source_name: str | None = None
    statement_scope: Literal["consolidated", "separate"] | None = None
    statement_status: Literal["original", "amended"] | None = None


class FinancialTrendResponse(BaseModel):
    symbol: str
    period_type: Literal["quarter", "year", "ttm"]
    statement_scope: Literal["consolidated", "separate"]
    periods: list[FinancialMetricResult]
    warnings: list[str] = Field(default_factory=list)


class FinancialStatementImportResult(BaseModel):
    inserted_periods: int
    updated_periods: int
    inserted_items: int
    updated_items: int
    rejected: int
    errors: list[str]


class ValuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    eps: float = Field(gt=0)
    bvps: float = Field(gt=0)
    pe_multiple: float = Field(gt=0, le=200)
    pb_multiple: float = Field(gt=0, le=50)
    bull_multiplier: float = Field(default=1.15, gt=0, le=3)
    base_multiplier: float = Field(default=1.0, gt=0, le=3)
    bear_multiplier: float = Field(default=0.8, gt=0, le=3)
    assumption_source: str = "user-assumption"


class ValuationResult(BaseModel):
    symbol: str
    method: str = "relative-pe-pb"
    scenarios: dict[str, float | None]
    assumptions: dict[str, object]
    warnings: list[str] = Field(default_factory=list)
    calculated_at: datetime


class DCFRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    forecast_free_cash_flows: list[float] = Field(min_length=1, max_length=10)
    discount_rate: float = Field(gt=0, lt=1)
    terminal_growth_rate: float = Field(ge=-0.5, lt=1)
    net_debt: float = 0
    shares_outstanding: float = Field(gt=0)
    bull_multiplier: float = Field(default=1.1, gt=0, le=3)
    bear_multiplier: float = Field(default=0.9, gt=0, le=3)
    assumption_source: str = Field(default="user-assumption", max_length=128)

    @model_validator(mode="after")
    def terminal_growth_must_be_lower_than_discount(self):
        if self.terminal_growth_rate >= self.discount_rate:
            raise ValueError("terminal_growth_rate must be lower than discount_rate")
        return self


class AnalystRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)
    question: str = Field(min_length=3, max_length=2000)


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(pattern="^E[0-9]{3,}$")
    kind: Literal["fact", "calculation", "interpretation", "hypothesis", "forecast"]
    statement: str
    source: str | None = None
    retrieved_at: datetime | None = None
    market_timestamp: datetime | None = None
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    symbol: str | None = None
    metric_key: str | None = None
    value: float | None = None
    unit: Literal[
        "vnd",
        "thousand_vnd",
        "million_vnd",
        "billion_vnd",
        "percent",
        "ratio",
        "count",
        "text",
    ] | None = None
    period: str | None = None


class FinancialClaim(BaseModel):
    """Machine-verifiable contract returned by an analyst model."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern="^C[0-9]{3,}$")
    claim_type: Literal[
        "fact", "financial_metric", "calculation", "interpretation", "forecast"
    ]
    symbol: str = Field(min_length=1, max_length=16)
    metric_key: str = Field(min_length=1, max_length=64)
    value: float | None = None
    unit: Literal[
        "vnd",
        "thousand_vnd",
        "million_vnd",
        "billion_vnd",
        "percent",
        "ratio",
        "count",
        "text",
    ]
    period: str = Field(min_length=1, max_length=64)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)
    interpretation: str = Field(min_length=1, max_length=500)
    confidence: Literal["high", "medium", "low"] = "medium"
    limitations: list[str] = Field(default_factory=list, max_length=10)


class StructuredClaimResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[FinancialClaim] = Field(default_factory=list, max_length=25)


class ClaimValidationError(BaseModel):
    claim_id: str
    code: Literal[
        "unknown_evidence",
        "symbol_mismatch",
        "metric_mismatch",
        "period_mismatch",
        "unit_mismatch",
        "value_mismatch",
        "missing_value",
        "unsupported_forecast",
    ]
    message: str


class ClaimVerificationResult(BaseModel):
    accepted: list[FinancialClaim] = Field(default_factory=list)
    rejected: list[ClaimValidationError] = Field(default_factory=list)


class AnalystResponse(BaseModel):
    status: Literal["available", "unavailable", "partial"]
    symbol: str
    answer: str
    sections: dict[str, list[str]] = Field(default_factory=dict)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    tool_outputs: dict[str, object] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)
    scheduled_for: datetime | None = None


class JobResult(BaseModel):
    id: int
    job_type: str
    symbol: str
    scheduled_for: datetime
    status: str
    attempts: int
    last_error: str | None = None


class WatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)


class WatchlistItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)


class AlertRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_type: Literal["technical_score", "news_event"]
    threshold: float | None = None
