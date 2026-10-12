"""Deterministic verification and rendering for model-proposed financial claims."""

from __future__ import annotations

from app.schemas import (
    ClaimValidationError,
    ClaimVerificationResult,
    EvidenceRecord,
    FinancialClaim,
)

_UNIT_DIMENSION = {
    "vnd": "currency",
    "thousand_vnd": "currency",
    "million_vnd": "currency",
    "billion_vnd": "currency",
    "percent": "percent",
    "ratio": "ratio",
    "count": "count",
    "text": "text",
}
_UNIT_TO_BASE = {
    "vnd": 1.0,
    "thousand_vnd": 1_000.0,
    "million_vnd": 1_000_000.0,
    "billion_vnd": 1_000_000_000.0,
    "percent": 1.0,
    "ratio": 1.0,
    "count": 1.0,
    "text": 1.0,
}


class ClaimVerificationService:
    """Accept claims only when their complete semantic identity matches evidence."""

    def __init__(self, *, relative_tolerance: float = 0.0001) -> None:
        self.relative_tolerance = relative_tolerance

    def verify(
        self, claims: list[FinancialClaim], evidence: list[EvidenceRecord]
    ) -> ClaimVerificationResult:
        by_id = {item.evidence_id: item for item in evidence}
        accepted: list[FinancialClaim] = []
        rejected: list[ClaimValidationError] = []
        for claim in claims:
            error = self._verify_one(claim, by_id)
            if error is None:
                accepted.append(claim)
            else:
                rejected.append(error)
        return ClaimVerificationResult(accepted=accepted, rejected=rejected)

    def _verify_one(
        self, claim: FinancialClaim, by_id: dict[str, EvidenceRecord]
    ) -> ClaimValidationError | None:
        records = [by_id[item] for item in claim.evidence_ids if item in by_id]
        if len(records) != len(set(claim.evidence_ids)):
            return self._error(claim, "unknown_evidence", "Claim tham chiếu evidence không tồn tại.")
        if not any((item.symbol or "").upper() == claim.symbol.upper() for item in records):
            return self._error(claim, "symbol_mismatch", "Evidence không khớp mã chứng khoán.")
        matching_metric = [item for item in records if item.metric_key == claim.metric_key]
        if not matching_metric:
            return self._error(claim, "metric_mismatch", "Evidence không khớp chỉ tiêu.")
        matching_period = [item for item in matching_metric if item.period == claim.period]
        if not matching_period:
            return self._error(claim, "period_mismatch", "Evidence không khớp kỳ dữ liệu.")
        compatible = [
            item
            for item in matching_period
            if item.unit and _UNIT_DIMENSION[item.unit] == _UNIT_DIMENSION[claim.unit]
        ]
        if not compatible:
            return self._error(claim, "unit_mismatch", "Đơn vị claim và evidence không tương thích.")
        if claim.claim_type == "forecast" and not any(item.kind == "forecast" for item in compatible):
            return self._error(
                claim,
                "unsupported_forecast",
                "Dự báo chỉ được chấp nhận khi có evidence dự báo tương ứng.",
            )
        if claim.value is None:
            if claim.unit != "text":
                return self._error(claim, "missing_value", "Claim định lượng thiếu giá trị.")
            return None
        observed = [item for item in compatible if item.value is not None]
        if not observed:
            return self._error(claim, "missing_value", "Evidence không có giá trị định lượng.")
        claim_base = claim.value * _UNIT_TO_BASE[claim.unit]
        for item in observed:
            evidence_base = float(item.value) * _UNIT_TO_BASE[item.unit or "text"]
            if abs(claim_base - evidence_base) <= max(
                0.01, abs(evidence_base) * self.relative_tolerance
            ):
                return None
        return self._error(claim, "value_mismatch", "Giá trị claim không khớp evidence.")

    @staticmethod
    def _error(
        claim: FinancialClaim, code: str, message: str
    ) -> ClaimValidationError:
        return ClaimValidationError(claim_id=claim.claim_id, code=code, message=message)

    @staticmethod
    def render_narrative(symbol: str, claims: list[FinancialClaim]) -> str:
        """Render only accepted fields; model prose never reaches the user directly."""
        if not claims:
            return f"Chưa có claim định lượng đã xác minh cho {symbol}."
        parts = []
        for claim in claims:
            value = ""
            if claim.value is not None:
                value = f" ({claim.value:g} {claim.unit})"
            citations = ", ".join(f"[{item}]" for item in claim.evidence_ids)
            parts.append(
                f"{claim.interpretation}{value}, kỳ {claim.period} {citations}."
            )
        return f"Các claim đã xác minh cho {symbol}: " + " ".join(parts)
