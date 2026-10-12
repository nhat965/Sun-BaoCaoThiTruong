from app.claim_verification import ClaimVerificationService
from app.schemas import EvidenceRecord, FinancialClaim


def evidence(**updates) -> EvidenceRecord:
    values = {
        "evidence_id": "E100",
        "kind": "calculation",
        "statement": "Doanh thu 2 tỷ VND",
        "symbol": "HPG",
        "metric_key": "revenue",
        "value": 2,
        "unit": "billion_vnd",
        "period": "2025",
    }
    return EvidenceRecord(**(values | updates))


def claim(**updates) -> FinancialClaim:
    values = {
        "claim_id": "C100",
        "claim_type": "calculation",
        "symbol": "HPG",
        "metric_key": "revenue",
        "value": 2_000,
        "unit": "million_vnd",
        "period": "2025",
        "evidence_ids": ["E100"],
        "interpretation": "Doanh thu được ghi nhận",
    }
    return FinancialClaim(**(values | updates))


def test_accepts_compatible_unit_conversion_and_renders_only_verified_claims():
    verifier = ClaimVerificationService()
    result = verifier.verify([claim()], [evidence()])
    assert result.rejected == []
    assert result.accepted[0].value == 2_000
    narrative = verifier.render_narrative("HPG", result.accepted)
    assert "2000 million_vnd" in narrative
    assert "[E100]" in narrative


def test_rejects_metric_period_unit_and_missing_evidence_independently():
    verifier = ClaimVerificationService()
    cases = [
        (claim(metric_key="profit"), "metric_mismatch"),
        (claim(period="2024"), "period_mismatch"),
        (claim(unit="percent", value=2), "unit_mismatch"),
        (claim(evidence_ids=["E999"]), "unknown_evidence"),
    ]
    for proposed, expected in cases:
        result = verifier.verify([proposed], [evidence()])
        assert result.rejected[0].code == expected


def test_rejects_unsupported_forecast_even_when_number_matches():
    result = ClaimVerificationService().verify(
        [claim(claim_type="forecast")],
        [evidence(kind="calculation")],
    )
    assert result.rejected[0].code == "unsupported_forecast"


def test_forecast_requires_and_accepts_forecast_evidence():
    result = ClaimVerificationService().verify(
        [claim(claim_type="forecast")],
        [evidence(kind="forecast")],
    )
    assert len(result.accepted) == 1


def test_rejects_price_target_without_forecast_source():
    target_evidence = evidence(
        metric_key="price_target", value=30_000, unit="vnd", kind="calculation"
    )
    target = claim(
        claim_type="forecast",
        metric_key="price_target",
        value=30_000,
        unit="vnd",
        interpretation="Giá mục tiêu",
    )
    result = ClaimVerificationService().verify([target], [target_evidence])
    assert result.rejected[0].code == "unsupported_forecast"


def test_rejects_missing_financial_value():
    result = ClaimVerificationService().verify(
        [claim()],
        [evidence(value=None)],
    )
    assert result.rejected[0].code == "missing_value"


def test_accepts_supported_non_numeric_explanation():
    explanation_evidence = evidence(
        metric_key="statement_status", value=None, unit="text", kind="fact"
    )
    explanation = claim(
        claim_type="interpretation",
        metric_key="statement_status",
        value=None,
        unit="text",
        interpretation="Báo cáo đang dùng là bản đã xác minh",
    )
    result = ClaimVerificationService().verify([explanation], [explanation_evidence])
    assert len(result.accepted) == 1
