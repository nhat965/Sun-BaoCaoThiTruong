from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.financial_normalization import (
    canonical_item_code,
    discrete_quarter_from_ytd,
    infer_period_start,
    normalize_currency,
    normalize_period_type,
)


def test_provider_labels_map_to_canonical_codes_and_keep_unknown_codes_stable():
    assert canonical_item_code("Doanh thu thuần") == "revenue"
    assert (
        canonical_item_code("Lợi nhuận sau thuế của cổ đông công ty mẹ")
        == "net_income_attributable_to_parent"
    )
    assert canonical_item_code("provider_custom_metric") == "provider_custom_metric"


def test_period_normalization_and_boundaries_are_explicit():
    assert normalize_period_type("Quý") == "quarter"
    assert normalize_period_type("lũy kế") == "ytd"
    assert normalize_period_type("annual") == "year"
    assert infer_period_start(
        datetime(2025, 9, 30, tzinfo=UTC), "quarter", 2025, 3
    ) == datetime(2025, 7, 1, tzinfo=UTC)
    assert infer_period_start(
        datetime(2025, 9, 30, tzinfo=UTC), "ttm", 2025, None
    ) is None


def test_ytd_to_quarter_conversion_does_not_double_count_cumulative_values():
    assert discrete_quarter_from_ytd(Decimal(240), Decimal(150)) == Decimal(90)
    assert discrete_quarter_from_ytd(Decimal(60), None) == Decimal(60)
    assert normalize_currency("vnd") == "VND"
    with pytest.raises(ValueError, match="three-letter"):
        normalize_currency("Vietnam Dong")
