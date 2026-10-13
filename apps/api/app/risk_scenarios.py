"""Evidence-first market risk signals and conditional scenarios."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.database import MarketRiskSignalRecord, MarketScenarioSnapshotRecord, SessionLocal
from app.market_trend import calculate_market_breadth, calculate_market_regime
from app.schemas import (
    MarketRiskSignal,
    MarketRisksResponse,
    MarketScenario,
    MarketScenariosResponse,
)
from app.sector_liquidity import calculate_liquidity

RISK_FORMULA_VERSION = "market-risk-v1"
SCENARIO_FORMULA_VERSION = "market-scenario-v1"


def _status(*values: str) -> str:
    if all(value == "available" for value in values):
        return "available"
    if any(value != "unavailable" for value in values):
        return "partial"
    return "unavailable"


def _context():
    breadth = calculate_market_breadth(persist=True)
    regime = calculate_market_regime(persist=True)
    liquidity = calculate_liquidity()
    return breadth, regime, liquidity


def _persist_signal(session_date: date, as_of: datetime, response: MarketRiskSignal, data_mode: str, validation: str) -> None:
    with SessionLocal() as session:
        existing = session.scalar(select(MarketRiskSignalRecord).where(MarketRiskSignalRecord.market_session_date == session_date, MarketRiskSignalRecord.signal_id == response.signal_id, MarketRiskSignalRecord.formula_version == RISK_FORMULA_VERSION))
        values = {"market_session_date": session_date, "as_of": as_of, "signal_id": response.signal_id, "signal_type": response.signal_type, "severity": response.severity, "title": response.title, "trigger_json": json.dumps(response.trigger, sort_keys=True), "evidence_json": json.dumps(response.evidence, ensure_ascii=False), "limitations_json": json.dumps(response.limitations, ensure_ascii=False), "data_mode": data_mode, "validation_status": validation, "formula_version": RISK_FORMULA_VERSION, "created_at": datetime.now(UTC)}
        if existing is None:
            session.add(MarketRiskSignalRecord(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()


def calculate_risks() -> MarketRisksResponse:
    breadth, regime, liquidity = _context()
    status = _status(breadth.data_status, regime.data_status, liquidity.data_status)
    signals: list[MarketRiskSignal] = []
    if regime.regime in {"DOWNTREND", "VOLATILE", "UNCERTAIN"}:
        signals.append(MarketRiskSignal(signal_id="trend-regime", signal_type="trend", severity="warning" if regime.regime == "DOWNTREND" else "watch", title=f"Chế độ thị trường {regime.regime}", trigger={"regime": regime.regime}, evidence=regime.evidence or [f"Regime hiện tại: {regime.regime}"], limitations=regime.limitations))
    if breadth.advance_decline_difference is not None and breadth.advance_decline_difference < 0:
        signals.append(MarketRiskSignal(signal_id="breadth-negative", signal_type="breadth", severity="warning", title="Độ rộng thị trường nghiêng về mã giảm", trigger={"advance_decline_difference": breadth.advance_decline_difference, "threshold": 0}, evidence=[f"Chênh lệch tăng/giảm: {breadth.advance_decline_difference} mã."], limitations=breadth.limitations))
    if breadth.above_ma20_percent is not None and breadth.above_ma20_percent < 50:
        signals.append(MarketRiskSignal(signal_id="breadth-ma20", signal_type="breadth", severity="watch", title="Tỷ lệ mã trên MA20 thấp", trigger={"above_ma20_percent": breadth.above_ma20_percent, "threshold_percent": 50}, evidence=[f"{breadth.above_ma20_percent}% mã nằm trên MA20."], limitations=breadth.limitations))
    if liquidity.relative_volume is not None and liquidity.relative_volume < 0.7:
        signals.append(MarketRiskSignal(signal_id="liquidity-contraction", signal_type="liquidity", severity="watch", title="Thanh khoản thấp hơn nền 20 phiên", trigger={"relative_volume": liquidity.relative_volume, "threshold": 0.7}, evidence=[f"Relative volume: {liquidity.relative_volume}x."], limitations=liquidity.limitations))
    if liquidity.decline_heavy_volume_count and liquidity.volume_expansion_count and liquidity.decline_heavy_volume_count > liquidity.volume_expansion_count:
        signals.append(MarketRiskSignal(signal_id="liquidity-decline-heavy", signal_type="liquidity", severity="warning", title="Khối lượng tập trung ở phiên giảm", trigger={"decline_heavy_count": liquidity.decline_heavy_volume_count, "expansion_count": liquidity.volume_expansion_count}, evidence=[f"{liquidity.decline_heavy_volume_count} mã giảm kèm volume lớn hơn số mã mở rộng volume {liquidity.volume_expansion_count}."], limitations=liquidity.limitations))
    if regime.conflicting_signals:
        signals.append(MarketRiskSignal(signal_id="regime-conflict", signal_type="regime_conflict", severity="watch", title="Các tín hiệu regime chưa đồng thuận", trigger={"conflict_count": len(regime.conflicting_signals)}, evidence=regime.conflicting_signals, limitations=regime.limitations))
    coverage = {"breadth": breadth.coverage.get("current_session_count", 0), "liquidity": liquidity.coverage.get("current_session_count", 0)}
    if any(float(value or 0) == 0 for value in coverage.values()):
        signals.append(MarketRiskSignal(signal_id="data-quality-coverage", signal_type="data_quality", severity="warning", title="Độ phủ dữ liệu hiện tại thấp", trigger=coverage, evidence=["Một hoặc nhiều khối phân tích không có quan sát phiên hiện tại."], limitations=[*breadth.limitations, *liquidity.limitations]))
    as_of = breadth.as_of or regime.as_of or liquidity.as_of
    session_date = breadth.market_session or regime.market_session or liquidity.market_session
    if as_of and session_date:
        for signal in signals:
            _persist_signal(date.fromisoformat(session_date), as_of, signal, breadth.data_mode, breadth.validation_status)
    limitations = sorted({*breadth.limitations, *regime.limitations, *liquidity.limitations, "Không có xác suất được hiệu chỉnh hoặc mục tiêu giá trong engine này."})
    return MarketRisksResponse(as_of=as_of, market_session=session_date, data_status=status, source="canonical-price-selection", coverage=coverage, signals=signals, warnings=[*breadth.warnings, *regime.warnings, *liquidity.warnings], limitations=limitations)


def _persist_scenario(session_date: date, as_of: datetime, item: MarketScenario, data_status: str, limitations: list[str]) -> None:
    with SessionLocal() as session:
        existing = session.scalar(select(MarketScenarioSnapshotRecord).where(MarketScenarioSnapshotRecord.market_session_date == session_date, MarketScenarioSnapshotRecord.scenario_id == item.scenario_id, MarketScenarioSnapshotRecord.formula_version == SCENARIO_FORMULA_VERSION))
        values = {"market_session_date": session_date, "as_of": as_of, "scenario_id": item.scenario_id, "label": item.label, "assumptions_json": json.dumps(item.assumptions, ensure_ascii=False), "evidence_json": json.dumps(item.evidence, ensure_ascii=False), "invalidation_json": json.dumps(item.invalidation_conditions, ensure_ascii=False), "risks_json": json.dumps(item.risks, ensure_ascii=False), "watch_json": json.dumps(item.watch, ensure_ascii=False), "data_status": data_status, "limitations_json": json.dumps(limitations, ensure_ascii=False), "formula_version": SCENARIO_FORMULA_VERSION, "created_at": datetime.now(UTC)}
        if existing is None:
            session.add(MarketScenarioSnapshotRecord(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.commit()


def calculate_scenarios() -> MarketScenariosResponse:
    breadth, regime, liquidity = _context()
    status = _status(breadth.data_status, regime.data_status, liquidity.data_status)
    evidence = [f"Regime: {regime.regime}", f"A/D difference: {breadth.advance_decline_difference}", f"Relative volume: {liquidity.relative_volume}"]
    limitations = sorted({*breadth.limitations, *regime.limitations, *liquidity.limitations, "Kịch bản là điều kiện quan sát, không phải dự báo xác suất."})
    scenarios = [
        MarketScenario(scenario_id="base", label="Phân hóa và duy trì trạng thái hiện tại", horizon="1-5 sessions", assumptions=["Regime không chuyển sang xu hướng mới", "Breadth và thanh khoản dao động quanh mức hiện tại"], evidence=evidence, invalidation_conditions=["A/D difference cải thiện rõ và MA breadth mở rộng", "A/D difference giảm sâu hoặc thanh khoản co mạnh"], risks=["Tín hiệu regime xung đột"], watch=["MA20 breadth", "relative volume"]),
        MarketScenario(scenario_id="positive", label="Độ rộng cải thiện", horizon="1-4 weeks", assumptions=["Tỷ lệ mã trên MA20 tăng trên ngưỡng hiện tại", "Khối lượng mở rộng đi cùng số mã tăng"], evidence=evidence, invalidation_conditions=["MA breadth suy yếu trong các phiên kế tiếp", "Decline-heavy volume tăng"], risks=["Dữ liệu chưa đủ phủ toàn thị trường"], watch=["advance/decline", "sector relative strength"]),
        MarketScenario(scenario_id="negative", label="Độ rộng suy yếu và rủi ro thanh khoản", horizon="1-4 weeks", assumptions=["A/D difference tiếp tục âm", "Thanh khoản giảm hoặc volume tập trung ở mã giảm"], evidence=evidence, invalidation_conditions=["Breadth đảo chiều dương cùng thanh khoản xác nhận"], risks=["Drawdown có thể tăng nếu regime chuyển DOWNTREND"], watch=["new lows", "relative volume", "regime conflicts"]),
    ]
    as_of = breadth.as_of or regime.as_of or liquidity.as_of
    session_date = breadth.market_session or regime.market_session or liquidity.market_session
    if as_of and session_date:
        for item in scenarios:
            _persist_scenario(date.fromisoformat(session_date), as_of, item, status, limitations)
    if status == "unavailable":
        scenarios = [item.model_copy(update={"status": "blocked"}) for item in scenarios]
    return MarketScenariosResponse(as_of=as_of, market_session=session_date, data_status=status, source="canonical-price-selection", scenarios=scenarios, warnings=[*breadth.warnings, *regime.warnings, *liquidity.warnings], limitations=limitations)
