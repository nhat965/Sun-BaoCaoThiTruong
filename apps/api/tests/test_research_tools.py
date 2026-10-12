from datetime import UTC, datetime

from app.research_tools import ResearchContext, ResearchToolRegistry, ToolName
from app.schemas import (
    AnalysisResponse,
    PriceBar,
    PriceSeries,
    Provenance,
    Security,
    TechnicalSnapshot,
)


def context() -> ResearchContext:
    security = Security(symbol="HPG", name="Hòa Phát", exchange="HOSE")
    prices = PriceSeries(
        security=security,
        interval="1d",
        adjusted=False,
        bars=[PriceBar(timestamp=datetime.now(UTC), open=10, high=11, low=9, close=10, volume=1)],
        provenance=Provenance(
            source="test",
            provider_symbol="HPG.TEST",
            retrieved_at=datetime.now(UTC),
            mode="fixture",
        ),
    )
    analysis = AnalysisResponse(
        security=security,
        latest_price=10,
        previous_close=None,
        change_percent=None,
        prices=prices,
        technicals=TechnicalSnapshot(
            calculated_at=datetime.now(UTC), sample_size=1, indicators={}
        ),
        news=[],
        summary=[],
        limitations=[],
        generated_at=datetime.now(UTC),
        evidence_count=1,
    )
    return ResearchContext(analysis=analysis, fundamentals=None, news=[])


def test_typed_plan_adds_requested_capabilities_only_from_registry():
    registry = ResearchToolRegistry()
    plan = registry.plan("Định giá HPG và so với ngành, thị trường thế nào?")
    assert ToolName.CALCULATE_VALUATION in plan
    assert ToolName.GET_SECTOR_CONTEXT in plan
    assert ToolName.GET_MARKET_OVERVIEW in plan
    assert all(isinstance(item, ToolName) for item in plan)


def test_unavailable_tools_return_explicit_limits_instead_of_fabricated_data():
    registry = ResearchToolRegistry()
    results = registry.execute(
        [ToolName.CALCULATE_FINANCIAL_METRICS, ToolName.GET_MARKET_OVERVIEW],
        context(),
    )
    assert results[ToolName.CALCULATE_FINANCIAL_METRICS].status == "unavailable"
    assert results[ToolName.GET_MARKET_OVERVIEW].data is None
    assert results[ToolName.GET_MARKET_OVERVIEW].limitations
