export type Signal = "positive" | "negative" | "neutral" | "unavailable";

export interface PriceBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Analysis {
  security: { symbol: string; name: string; exchange: string; currency: string };
  latest_price: number;
  previous_close: number | null;
  change_percent: number | null;
  prices: {
    bars: PriceBar[];
    provenance: {
      source: string;
      source_url: string | null;
      retrieved_at: string;
      market_timestamp: string | null;
      mode: "live" | "fixture";
      delayed: boolean;
      notes: string | null;
    };
  };
  technicals: {
    formula_version: string;
    calculated_at: string;
    sample_size: number;
    indicators: Record<string, { value: number | null; signal: Signal; explanation: string }>;
    component_scores: Record<string, number | null>;
    conflicts: string[];
  };
  news: { title: string; publisher: string; published_at: string | null; url: string; event_category: string; relevance_score: number }[];
  summary: string[];
  limitations: string[];
  generated_at: string;
  evidence_count: number;
  fundamental_status: "available" | "partial" | "unavailable";
  fundamental_message: string;
  bullish_factors: string[];
  bearish_factors: string[];
  scenarios: Record<string, string[]>;
}

export interface FinancialMetricResult {
  metrics: Record<string, number | null>;
  calculated_at: string;
  formula_version: string;
  warnings: string[];
  symbol: string | null;
  period_type: string | null;
  period_end: string | null;
  source_name: string | null;
  statement_scope: "consolidated" | "separate" | null;
  statement_status: "original" | "amended" | null;
  metric_metadata: Record<string, FinancialMetricMetadata>;
}

export interface FinancialMetricMetadata {
  metric_code: string;
  value: number | null;
  unit: string;
  formula_version: string;
  required_inputs: string[];
  missing_inputs: string[];
  input_status: "complete" | "incomplete" | "not_applicable";
  applicable_company_types: string[];
  period_policy: string;
  limitations: string;
  as_of_date: string | null;
}

export interface FinancialTrendResponse {
  symbol: string;
  period_type: "quarter" | "year" | "ttm";
  statement_scope: "consolidated" | "separate";
  periods: FinancialMetricResult[];
  warnings: string[];
}

export interface ValuationResult {
  symbol: string;
  method: string;
  scenarios: Record<string, number | null>;
  assumptions: Record<string, unknown>;
  warnings: string[];
  calculated_at: string;
}

export interface AnalystResponse {
  status: "available" | "partial" | "unavailable";
  symbol: string;
  answer: string;
  sections: Record<string, string[]>;
  evidence?: {
    evidence_id: string;
    kind: "fact" | "calculation" | "interpretation" | "hypothesis" | "forecast";
    statement: string;
    source: string | null;
    retrieved_at: string | null;
    market_timestamp: string | null;
    confidence: "high" | "medium" | "low" | "unknown";
  }[];
  limitations: string[];
}

export interface DataQualityReport {
  generated_at: string;
  market_data_mode: "live" | "fixture";
  securities_count: number;
  active_securities_count: number;
  exchange_distribution: Record<string, number>;
  price_observations_count: number;
  symbols_with_price_history: number;
  symbols_missing_price_history: number;
  symbols_with_financial_statements: number;
  symbols_missing_financial_statements: number;
  price_coverage_percent: number;
  financial_coverage_percent: number;
  missing_price_symbols: string[];
  missing_financial_symbols: string[];
  sync_error_records: number;
  failed_sync_symbols: string[];
  price_quality_alerts: Record<string, number>;
  latest_market_timestamp_by_exchange: Record<string, string | null>;
  last_market_timestamp: string | null;
  last_retrieval_timestamp: string | null;
  sources: {
    name: string;
    capabilities: string[];
    availability: "available" | "configured" | "unavailable" | "fixture";
    freshness: string;
    licensing: string;
    last_checked_at: string | null;
    last_success_at: string | null;
    last_failure_at: string | null;
    consecutive_failures: number;
    message: string | null;
  }[];
  issues: string[];
}

export interface FinancialStatementItem {
  statement_type: "income" | "balance" | "cash_flow";
  item_code: string;
  value: number;
  unit: string;
  raw_value: number | null;
  raw_unit: string | null;
  source_name: string;
  source_url: string | null;
  verification_status: "verified" | "unverified" | "rejected";
  updated_at: string;
}

export interface FinancialStatementPeriod {
  period_end: string;
  period_type: "quarter" | "year" | "ttm";
  fiscal_year: number;
  fiscal_quarter: number | null;
  reported_at: string | null;
  statement_scope: "consolidated" | "separate";
  statement_status: "original" | "amended";
  currency: string;
  source_name: string;
  source_url: string | null;
  verification_status: "verified" | "unverified" | "rejected";
  updated_at: string;
  items: FinancialStatementItem[];
}

export interface FinancialStatementsResponse {
  symbol: string;
  automatic_sync_status: "available" | "live" | "blocked";
  automatic_sync_message: string;
  periods: FinancialStatementPeriod[];
}

export interface SecuritiesExplorerItem {
  symbol: string;
  name: string;
  exchange: string;
  industry: string | null;
  sector: string | null;
  listing_status: "active" | "inactive" | "delisted" | "suspended";
  currency: string;
  latest_price: number | null;
  change_percent: number | null;
  volume: number | null;
  trading_value: number | null;
  pe: number | null;
  pb: number | null;
  price_updated_at: string | null;
  market_session_date: string | null;
  price_retrieved_at: string | null;
  price_source: string | null;
  price_source_mode: string | null;
  price_validation_status: string | null;
  price_trust_status: "trusted" | "development_only" | "fixture" | null;
  price_is_stale: boolean | null;
  registry_updated_at: string;
}

export interface SecuritiesExplorerResponse {
  items: SecuritiesExplorerItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  available_exchanges: string[];
  available_sectors: string[];
  available_listing_statuses: string[];
  generated_at: string;
}

