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
  news: { title: string; publisher: string; published_at: string | null; url: string }[];
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
}

export interface AnalystResponse {
  status: "available" | "partial" | "unavailable";
  symbol: string;
  answer: string;
  sections: Record<string, string[]>;
  limitations: string[];
}

export interface DataQualityReport {
  generated_at: string;
  market_data_mode: "live" | "fixture";
  securities_count: number;
  active_securities_count: number;
  price_observations_count: number;
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

