from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Provenance(BaseModel):
    source: str
    provider_id: str | None = None
    source_url: str | None = None
    provider_symbol: str
    retrieved_at: datetime
    market_timestamp: datetime | None = None
    mode: Literal["live", "fixture"]
    delayed: bool = True
    validation_status: Literal["valid", "partial", "invalid"] = "valid"
    adjustment_policy: str = "unadjusted"
    coverage: str = "security"
    freshness: str = "unknown"
    last_updated: datetime | None = None
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
    actual_trading_value: float | None = None
    market_cap: float | None = None


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


class ProviderCapabilityStatus(BaseModel):
    provider_id: str
    name: str
    documentation_url: str | None = None
    documented_capabilities: list[str] = Field(default_factory=list)
    enabled_capabilities: list[str] = Field(default_factory=list)
    authentication: str
    access_requirements: str
    licensing: str
    availability: Literal["available", "configured", "blocked", "fixture"]
    last_success_at: datetime | None = None
    last_checked_at: datetime | None = None
    test_result: str
    cost_and_limits: str


class DataSyncRun(BaseModel):
    id: int
    provider: str
    capability: str
    symbol: str | None = None
    sync_mode: Literal["initial", "incremental"]
    status: Literal["RUNNING", "SUCCESS", "PARTIAL", "FAILED", "BLOCKED"]
    started_at: datetime
    finished_at: datetime | None = None
    cursor_from: datetime | None = None
    cursor_to: datetime | None = None
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    error_message: str | None = None
    details: dict = Field(default_factory=dict)


class DataQualityReport(BaseModel):
    generated_at: datetime
    market_data_mode: Literal["live", "fixture"]
    securities_count: int
    active_securities_count: int
    exchange_distribution: dict[str, int] = Field(default_factory=dict)
    price_observations_count: int
    symbols_with_price_history: int = 0
    symbols_missing_price_history: int = 0
    symbols_with_financial_statements: int = 0
    symbols_missing_financial_statements: int = 0
    price_coverage_percent: float = Field(default=0, ge=0, le=100)
    financial_coverage_percent: float = Field(default=0, ge=0, le=100)
    missing_price_symbols: list[str] = Field(default_factory=list)
    missing_financial_symbols: list[str] = Field(default_factory=list)
    sync_error_records: int = 0
    failed_sync_symbols: list[str] = Field(default_factory=list)
    price_quality_alerts: dict[str, int] = Field(default_factory=dict)
    latest_market_timestamp_by_exchange: dict[str, datetime | None] = Field(
        default_factory=dict
    )
    last_market_timestamp: datetime | None = None
    last_retrieval_timestamp: datetime | None = None
    active_stock_count: int = 0
    stocks_with_20_sessions: int = 0
    stocks_with_50_sessions: int = 0
    stocks_with_200_sessions: int = 0
    stocks_with_market_cap: int = 0
    stocks_with_foreign_flow: int = 0
    universe_coverage_by_exchange: dict[str, dict[str, int | float]] = Field(
        default_factory=dict
    )
    market_index_coverage: dict[str, int | float] = Field(default_factory=dict)
    sources: list[SourceDiagnostic]
    issues: list[str] = Field(default_factory=list)


class SecuritiesImportResult(BaseModel):
    inserted: int
    updated: int
    rejected: int
    errors: list[str]


class SecuritiesExplorerItem(BaseModel):
    symbol: str
    name: str
    exchange: str
    industry: str | None = None
    sector: str | None = None
    listing_status: Literal["active", "inactive", "delisted", "suspended"]
    currency: str
    latest_price: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    trading_value: float | None = None
    pe: float | None = None
    pb: float | None = None
    price_updated_at: datetime | None = None
    market_session_date: date | None = None
    price_retrieved_at: datetime | None = None
    price_source: str | None = None
    price_source_mode: str | None = None
    price_validation_status: str | None = None
    price_trust_status: Literal["trusted", "development_only", "fixture"] | None = None
    price_is_stale: bool | None = None
    registry_updated_at: datetime


class SecuritiesExplorerResponse(BaseModel):
    items: list[SecuritiesExplorerItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    available_exchanges: list[str] = Field(default_factory=list)
    available_sectors: list[str] = Field(default_factory=list)
    available_listing_statuses: list[str] = Field(default_factory=list)
    generated_at: datetime


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

    entity_type: Literal["non_financial", "bank", "securities", "insurance"] = (
        "non_financial"
    )
    revenue: float | None = None
    prior_revenue: float | None = None
    previous_period_revenue: float | None = None
    ttm_revenue: float | None = None
    net_income: float | None = None
    net_income_attributable_to_parent: float | None = None
    prior_net_income: float | None = None
    previous_period_net_income: float | None = None
    ttm_net_income: float | None = None
    period_months: int | None = Field(default=None, ge=1, le=12)
    total_assets: float | None = None
    prior_total_assets: float | None = None
    total_equity: float | None = None
    prior_total_equity: float | None = None
    total_debt: float | None = None
    prior_total_debt: float | None = None
    cash_and_equivalents: float | None = None
    prior_cash_and_equivalents: float | None = None
    current_assets: float | None = None
    inventory: float | None = None
    current_liabilities: float | None = None
    operating_income: float | None = None
    profit_before_tax: float | None = None
    tax_expense: float | None = None
    gross_profit: float | None = None
    interest_expense: float | None = None
    operating_cash_flow: float | None = None
    ttm_operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    ttm_capital_expenditure: float | None = None
    shares_outstanding: float | None = None
    diluted_shares_outstanding: float | None = None
    market_price: float | None = None
    enterprise_value: float | None = None
    ebitda: float | None = None


class FinancialMetricMetadata(BaseModel):
    metric_code: str
    value: float | None
    unit: str
    formula_version: str
    required_inputs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    input_status: Literal["complete", "incomplete", "not_applicable"]
    applicable_company_types: list[str] = Field(default_factory=list)
    period_policy: str
    limitations: str
    as_of_date: datetime | None = None


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
    metric_metadata: dict[str, FinancialMetricMetadata] = Field(default_factory=dict)


class FinancialTrendResponse(BaseModel):
    symbol: str
    period_type: Literal["quarter", "year", "ytd", "ttm"]
    statement_scope: Literal["consolidated", "separate"]
    periods: list[FinancialMetricResult]
    warnings: list[str] = Field(default_factory=list)


class FinancialStatementImportResult(BaseModel):
    inserted_periods: int
    updated_periods: int
    inserted_items: int
    updated_items: int
    skipped_items: int = 0
    rejected: int
    errors: list[str]
    validation_reports: list["FinancialValidationReport"] = Field(default_factory=list)


class FinancialValidationIssue(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    item_code: str | None = None
    source_name: str | None = None


class FinancialValidationReport(BaseModel):
    symbol: str
    period_end: datetime
    period_type: Literal["quarter", "year", "ytd", "ttm"]
    statement_scope: Literal["consolidated", "separate"]
    statement_status: Literal["original", "amended"]
    source_name: str
    source_url: str | None = None
    checks: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_status: Literal[
        "valid", "warning", "invalid", "insufficient_data", "rejected"
    ]
    issues: list[FinancialValidationIssue] = Field(default_factory=list)
    created_at: datetime


class FinancialStatementItem(BaseModel):
    statement_type: Literal["income", "balance", "cash_flow"]
    item_code: str
    raw_item_code: str | None = None
    mapping_version: str = "financial-map-v1"
    value: float
    unit: str
    raw_value: float | None = None
    raw_unit: str | None = None
    source_name: str
    source_url: str | None = None
    verification_status: Literal["verified", "unverified", "rejected"]
    updated_at: datetime


class FinancialStatementPeriod(BaseModel):
    period_start: datetime | None = None
    period_end: datetime
    period_type: Literal["quarter", "year", "ytd", "ttm"]
    fiscal_year: int
    fiscal_quarter: int | None = None
    reported_at: datetime | None = None
    statement_scope: Literal["consolidated", "separate"]
    statement_status: Literal["original", "amended"]
    accounting_standard: str = "unknown"
    currency: str
    source_name: str
    source_url: str | None = None
    verification_status: Literal["verified", "unverified", "rejected"]
    retrieved_at: datetime | None = None
    validated_at: datetime | None = None
    data_version: str = "financial-v1"
    content_hash: str | None = None
    updated_at: datetime
    items: list[FinancialStatementItem]


class FinancialStatementsResponse(BaseModel):
    symbol: str
    automatic_sync_status: Literal["available", "blocked"]
    automatic_sync_message: str
    periods: list[FinancialStatementPeriod]


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


class DCFSensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    forecast_free_cash_flows: list[float] = Field(min_length=1, max_length=10)
    discount_rates: list[float] = Field(min_length=2, max_length=10)
    terminal_growth_rates: list[float] = Field(min_length=2, max_length=10)
    net_debt: float = 0
    shares_outstanding: float = Field(gt=0)
    assumption_source: str = Field(default="user-assumption", max_length=128)

    @model_validator(mode="after")
    def validate_sensitivity_rates(self):
        if any(rate <= 0 or rate >= 1 for rate in self.discount_rates):
            raise ValueError("discount_rates must be between 0 and 1")
        if any(rate < -0.5 or rate >= 1 for rate in self.terminal_growth_rates):
            raise ValueError("terminal_growth_rates must be between -0.5 and 1")
        return self


class DCFSensitivityResult(BaseModel):
    symbol: str
    discount_rates: list[float]
    terminal_growth_rates: list[float]
    values: dict[str, dict[str, float | None]]
    assumptions: dict[str, object]
    warnings: list[str] = Field(default_factory=list)
    calculated_at: datetime


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
    research_plan: list[str] = Field(default_factory=list)
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
    next_attempt_at: datetime | None = None


class MarketIndexObservation(BaseModel):
    symbol: str
    name: str
    close: float
    change_percent: float | None = None
    market_timestamp: datetime
    source: str
    provider: str | None = None
    source_url: str | None = None
    market_session: str | None = None
    retrieved_at: datetime | None = None
    last_updated: datetime | None = None
    data_mode: Literal[
        "live", "delayed", "historical", "stale", "fixture", "unavailable"
    ] = "unavailable"
    validation_status: Literal["valid", "partial", "unvalidated", "invalid"] = "unvalidated"
    coverage: str = "index"
    freshness: str = "unknown"
    adjustment_policy: str = "unknown"


class MarketIndicesResponse(BaseModel):
    as_of: datetime | None = None
    market_session: str | None = None
    data_status: Literal["available", "partial", "unavailable"] = "unavailable"
    source: str | None = None
    coverage: dict[str, int | float] = Field(default_factory=dict)
    indices: list[MarketIndexObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    formula_version: str = "market-foundation-v1"


class MarketBreadthPoint(BaseModel):
    market_session: str
    advancers: int
    decliners: int
    unchanged: int
    traded_securities: int
    above_ma20_percent: float | None = None
    above_ma50_percent: float | None = None
    above_ma200_percent: float | None = None


class MarketBreadthResponse(BaseModel):
    as_of: datetime | None = None
    market_session: str | None = None
    data_status: Literal["available", "partial", "unavailable"] = "unavailable"
    source: str | None = None
    data_mode: str = "unavailable"
    validation_status: str = "unvalidated"
    freshness: str = "unknown"
    coverage: dict[str, int | float] = Field(default_factory=dict)
    advancers: int | None = None
    decliners: int | None = None
    unchanged: int | None = None
    traded_securities: int | None = None
    advance_decline_ratio: float | None = None
    advance_decline_difference: int | None = None
    above_ma20: int | None = None
    above_ma20_denominator: int | None = None
    above_ma20_percent: float | None = None
    above_ma50: int | None = None
    above_ma50_denominator: int | None = None
    above_ma50_percent: float | None = None
    above_ma200: int | None = None
    above_ma200_denominator: int | None = None
    above_ma200_percent: float | None = None
    new_highs_20: int | None = None
    new_lows_20: int | None = None
    divergences: list[str] = Field(default_factory=list)
    historical: list[MarketBreadthPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    formula_version: str = "market-breadth-v1"


class MarketRegimeResponse(BaseModel):
    as_of: datetime | None = None
    market_session: str | None = None
    data_status: Literal["available", "partial", "unavailable"] = "unavailable"
    source: str | None = None
    data_mode: str = "unavailable"
    validation_status: str = "unvalidated"
    freshness: str = "unknown"
    regime: Literal["UPTREND", "DOWNTREND", "SIDEWAYS", "VOLATILE", "UNCERTAIN"] = "UNCERTAIN"
    indicators: dict[str, float | int | str | None] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    conflicting_signals: list[str] = Field(default_factory=list)
    coverage: dict[str, int | float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    formula_version: str = "market-regime-v1"


class SectorMetric(BaseModel):
    sector_id: str
    sector_name: str
    taxonomy_version: str = "registry-v1"
    stock_count: int = 0
    eligible_1d: int = 0
    eligible_5d: int = 0
    eligible_20d: int = 0
    advancers: int = 0
    decliners: int = 0
    unchanged: int = 0
    performance_1d_percent: float | None = None
    performance_5d_percent: float | None = None
    performance_20d_percent: float | None = None
    volume: int | None = None
    average_volume_5: float | None = None
    average_volume_10: float | None = None
    average_volume_20: float | None = None
    relative_volume: float | None = None
    actual_trading_value: float | None = None
    estimated_trading_value: float | None = None
    relative_strength_vs_vnindex_percent: float | None = None
    above_ma20_percent: float | None = None
    above_ma50_percent: float | None = None
    coverage: dict[str, int | float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class SectorIntelligenceResponse(BaseModel):
    as_of: datetime | None = None
    market_session: str | None = None
    data_status: Literal["available", "partial", "unavailable"] = "unavailable"
    source: str | None = None
    data_mode: str = "unavailable"
    validation_status: str = "unvalidated"
    taxonomy_version: str = "registry-v1"
    coverage: dict[str, int | float] = Field(default_factory=dict)
    sort_by: str = "performance_1d"
    sectors: list[SectorMetric] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    formula_version: str = "sector-intelligence-v1"


class LiquidityLeader(BaseModel):
    symbol: str
    sector: str | None = None
    volume: int | None = None
    actual_trading_value: float | None = None
    return_1d_percent: float | None = None
    relative_volume: float | None = None


class LiquidityResponse(BaseModel):
    as_of: datetime | None = None
    market_session: str | None = None
    data_status: Literal["available", "partial", "unavailable"] = "unavailable"
    source: str | None = None
    data_mode: str = "unavailable"
    validation_status: str = "unvalidated"
    coverage: dict[str, int | float] = Field(default_factory=dict)
    total_volume: int | None = None
    average_volume_5: float | None = None
    average_volume_10: float | None = None
    average_volume_20: float | None = None
    relative_volume: float | None = None
    total_actual_trading_value: float | None = None
    average_actual_trading_value_5: float | None = None
    average_actual_trading_value_10: float | None = None
    average_actual_trading_value_20: float | None = None
    top5_volume_share_percent: float | None = None
    top10_volume_share_percent: float | None = None
    top5_trading_value_share_percent: float | None = None
    top10_trading_value_share_percent: float | None = None
    volume_expansion_count: int | None = None
    decline_heavy_volume_count: int | None = None
    leaders: list[LiquidityLeader] = Field(default_factory=list)
    foreign_net_value: float | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    formula_version: str = "liquidity-intelligence-v1"


class MarketOverview(BaseModel):
    status: Literal["available", "partial", "unavailable"]
    as_of: datetime | None = None
    source_mode: Literal["live", "fixture", "mixed", "unknown"] = "unknown"
    sources: list[str] = Field(default_factory=list)
    active_stock_count: int = 0
    stocks_with_two_sessions: int = 0
    coverage_percent: float = Field(default=0, ge=0, le=100)
    advancers: int | None = None
    decliners: int | None = None
    unchanged: int | None = None
    total_volume: int | None = None
    estimated_trading_value: float | None = None
    actual_trading_value: float | None = None
    indices: list[MarketIndexObservation] = Field(default_factory=list)
    sector_performance_percent: dict[str, float] = Field(default_factory=dict)
    foreign_net_value: float | None = None
    limitations: list[str] = Field(default_factory=list)


class DailyMarketReport(BaseModel):
    snapshot_key: str
    report_type: Literal["pre_market", "post_market", "stock_eod"]
    symbol: str | None = None
    trading_date: datetime
    source_mode: str
    sections: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime


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


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    base_currency: str = Field(default="VND", min_length=3, max_length=8)


class PortfolioTransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)
    transaction_type: Literal["buy", "sell", "dividend"]
    quantity: float = Field(default=0, ge=0)
    price: float = Field(default=0, ge=0)
    fees: float = Field(default=0, ge=0)
    cash_amount: float = Field(default=0, ge=0)
    executed_at: datetime
    external_id: str = Field(min_length=1, max_length=128)
    source_name: str = Field(default="manual", min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_transaction_values(self):
        if self.transaction_type in {"buy", "sell"} and (
            self.quantity <= 0 or self.price <= 0
        ):
            raise ValueError("buy/sell require positive quantity and price")
        if self.transaction_type == "dividend" and self.cash_amount <= 0:
            raise ValueError("dividend requires positive cash_amount")
        if self.executed_at.tzinfo is None:
            raise ValueError("executed_at must include a timezone")
        return self


class PortfolioImportResult(BaseModel):
    inserted: int
    skipped: int
    rejected: int
    errors: list[str] = Field(default_factory=list)


class PortfolioPosition(BaseModel):
    symbol: str
    sector: str | None = None
    quantity: float
    average_cost: float
    cost_basis: float
    latest_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float
    weight_percent: float | None = None


class PortfolioSummary(BaseModel):
    id: int
    name: str
    base_currency: str
    positions: list[PortfolioPosition] = Field(default_factory=list)
    total_cost_basis: float
    total_market_value: float | None = None
    realized_pnl: float
    unrealized_pnl: float | None = None
    sector_allocation_percent: dict[str, float] = Field(default_factory=dict)
    concentration_percent: float | None = None
    herfindahl_index: float | None = None
    limitations: list[str] = Field(default_factory=list)
    calculated_at: datetime


class SocialContentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=5000)
    source_name: str = Field(default="user-supplied", min_length=1, max_length=128)
    published_at: datetime | None = None


class SocialClassification(BaseModel):
    symbol: str
    sentiment: Literal["positive", "negative", "neutral", "mixed", "uncertain"]
    content_type: Literal[
        "technical_opinion",
        "fundamental_opinion",
        "rumor",
        "forecast",
        "promotional",
        "question",
        "other",
    ]
    confidence: Literal["low", "medium"]
    matched_terms: list[str] = Field(default_factory=list)
    source_name: str
    published_at: datetime | None = None
    uncertainty: list[str] = Field(default_factory=list)


class SocialBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SocialContentItem] = Field(min_length=1, max_length=500)


class SocialBatchResult(BaseModel):
    sample_size: int
    sentiment_distribution: dict[str, int]
    type_distribution: dict[str, int]
    items: list[SocialClassification]
    coverage_note: str
    generated_at: datetime
