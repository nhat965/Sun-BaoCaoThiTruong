"""Typed, deterministic research-tool planning over implemented application data."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas import AnalysisResponse, FinancialMetricResult, NewsItem


class ToolName(StrEnum):
    SEARCH_SECURITY = "search_security"
    GET_PRICES = "get_prices"
    GET_TECHNICAL_INDICATORS = "get_technical_indicators"
    GET_FINANCIAL_STATEMENTS = "get_financial_statements"
    CALCULATE_FINANCIAL_METRICS = "calculate_financial_metrics"
    CALCULATE_VALUATION = "calculate_valuation"
    SEARCH_NEWS = "search_news"
    GET_SECTOR_CONTEXT = "get_sector_context"
    GET_MARKET_OVERVIEW = "get_market_overview"
    GET_SOURCE_EVIDENCE = "get_source_evidence"


class ToolExecution(BaseModel):
    name: ToolName
    status: str
    data: object | None = None
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ResearchContext:
    analysis: AnalysisResponse
    fundamentals: FinancialMetricResult | None
    news: list[NewsItem]


class ResearchToolRegistry:
    """Closed registry: plans can contain only these implemented tool names."""

    def plan(self, question: str) -> list[ToolName]:
        normalized = question.casefold()
        tools = [
            ToolName.SEARCH_SECURITY,
            ToolName.GET_PRICES,
            ToolName.GET_TECHNICAL_INDICATORS,
            ToolName.GET_FINANCIAL_STATEMENTS,
            ToolName.CALCULATE_FINANCIAL_METRICS,
            ToolName.SEARCH_NEWS,
            ToolName.GET_SOURCE_EVIDENCE,
        ]
        if any(term in normalized for term in ("định giá", "valuation", "mục tiêu")):
            tools.append(ToolName.CALCULATE_VALUATION)
        if any(term in normalized for term in ("ngành", "sector")):
            tools.append(ToolName.GET_SECTOR_CONTEXT)
        if any(term in normalized for term in ("thị trường", "vn-index", "market")):
            tools.append(ToolName.GET_MARKET_OVERVIEW)
        return tools

    def execute(
        self, plan: list[ToolName], context: ResearchContext
    ) -> dict[str, ToolExecution]:
        return {name.value: self._execute_one(name, context) for name in plan}

    def _execute_one(self, name: ToolName, context: ResearchContext) -> ToolExecution:
        analysis = context.analysis
        if name == ToolName.SEARCH_SECURITY:
            return self._available(name, analysis.security.model_dump(mode="json"))
        if name == ToolName.GET_PRICES:
            return self._available(
                name,
                {
                    "latest_price": analysis.latest_price,
                    "previous_close": analysis.previous_close,
                    "change_percent": analysis.change_percent,
                    "provenance": analysis.prices.provenance.model_dump(mode="json"),
                },
            )
        if name == ToolName.GET_TECHNICAL_INDICATORS:
            return self._available(name, analysis.technicals.model_dump(mode="json"))
        if name in {
            ToolName.GET_FINANCIAL_STATEMENTS,
            ToolName.CALCULATE_FINANCIAL_METRICS,
        }:
            if context.fundamentals is None:
                return self._unavailable(name, "Chưa có BCTC đã xác minh cho mã này.")
            return self._available(name, context.fundamentals.model_dump(mode="json"))
        if name == ToolName.SEARCH_NEWS:
            return self._available(
                name, [item.model_dump(mode="json") for item in context.news]
            )
        if name == ToolName.GET_SOURCE_EVIDENCE:
            return self._available(
                name,
                {
                    "price_source": analysis.prices.provenance.model_dump(mode="json"),
                    "financial_source": (
                        context.fundamentals.source_name if context.fundamentals else None
                    ),
                    "news_sources": sorted({item.publisher for item in context.news}),
                },
            )
        if name == ToolName.CALCULATE_VALUATION:
            return self._unavailable(
                name,
                "Định giá cần giả định rõ ràng từ người dùng; analyst không tự tạo đầu vào.",
            )
        if name == ToolName.GET_SECTOR_CONTEXT:
            return self._unavailable(name, "Chưa có bộ dữ liệu sector benchmark đã xác minh.")
        if name == ToolName.GET_MARKET_OVERVIEW:
            return self._unavailable(name, "Chưa có feed chỉ số và market breadth được cấp phép.")
        raise ValueError(f"Tool is not registered: {name}")

    @staticmethod
    def _available(name: ToolName, data: object) -> ToolExecution:
        return ToolExecution(name=name, status="available", data=data)

    @staticmethod
    def _unavailable(name: ToolName, reason: str) -> ToolExecution:
        return ToolExecution(name=name, status="unavailable", limitations=[reason])
