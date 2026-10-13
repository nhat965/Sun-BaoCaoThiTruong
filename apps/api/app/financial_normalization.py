"""Canonical financial-period and line-item normalization rules.

Provider adapters may use different labels for the same Vietnamese financial
line.  This module keeps the mapping deterministic and versioned while
preserving the provider's original label for auditability.
"""

import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import Decimal

MAPPING_VERSION = "financial-map-v1"
PERIOD_TYPES = frozenset({"quarter", "year", "ytd", "ttm"})


def _token(value: str) -> str:
    translated = value.strip().lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


_ITEM_ALIASES = {
    "doanh_thu": "revenue",
    "doanh_thu_thuan": "revenue",
    "net_revenue": "revenue",
    "revenue": "revenue",
    "gia_von": "cost_of_goods_sold",
    "cost_of_goods_sold": "cost_of_goods_sold",
    "loi_nhuan_gop": "gross_profit",
    "gross_profit": "gross_profit",
    "loi_nhuan_thuan_tu_hoat_dong_kinh_doanh": "operating_income",
    "operating_income": "operating_income",
    "loi_nhuan_truoc_thue": "profit_before_tax",
    "profit_before_tax": "profit_before_tax",
    "chi_phi_thue_thu_nhap_doanh_nghiep": "income_tax_expense",
    "income_tax_expense": "income_tax_expense",
    "loi_nhuan_sau_thue": "net_income",
    "net_income": "net_income",
    "loi_nhuan_sau_thue_cua_co_dong_cong_ty_me": "net_income_attributable_to_parent",
    "net_income_attributable_to_parent": "net_income_attributable_to_parent",
    "tong_tai_san": "total_assets",
    "total_assets": "total_assets",
    "tong_no_phai_tra": "total_liabilities",
    "total_liabilities": "total_liabilities",
    "von_chu_so_huu": "total_equity",
    "total_equity": "total_equity",
    "tien_va_tuong_duong_tien": "cash_and_equivalents",
    "cash_and_equivalents": "cash_and_equivalents",
    "hang_ton_kho": "inventory",
    "inventory": "inventory",
    "cac_khoan_phai_thu": "accounts_receivable",
    "accounts_receivable": "accounts_receivable",
    "no_vay_ngan_han": "short_term_borrowings",
    "short_term_borrowings": "short_term_borrowings",
    "no_vay_dai_han": "long_term_borrowings",
    "long_term_borrowings": "long_term_borrowings",
    "luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh": "operating_cash_flow",
    "operating_cash_flow": "operating_cash_flow",
    "luu_chuyen_tien_tu_hoat_dong_dau_tu": "investing_cash_flow",
    "investing_cash_flow": "investing_cash_flow",
    "luu_chuyen_tien_tu_hoat_dong_tai_chinh": "financing_cash_flow",
    "financing_cash_flow": "financing_cash_flow",
    "chi_tieu_mua_sam_tai_san_co_dinh": "capital_expenditure",
    "capital_expenditure": "capital_expenditure",
    "so_co_phieu_luu_hanh": "shares_outstanding",
    "shares_outstanding": "shares_outstanding",
    "co_phieu_binh_quan_gia_quyen": "weighted_average_shares",
    "weighted_average_shares": "weighted_average_shares",
}

_PERIOD_ALIASES = {
    "q": "quarter",
    "quy": "quarter",
    "quarter": "quarter",
    "quarterly": "quarter",
    "y": "year",
    "nam": "year",
    "year": "year",
    "annual": "year",
    "ytd": "ytd",
    "luy_ke": "ytd",
    "luy_ke_nam": "ytd",
    "ttm": "ttm",
}


def canonical_item_code(raw_code: str) -> str:
    """Return a stable canonical code while retaining unknown codes losslessly."""

    token = _token(raw_code)
    if not token:
        raise ValueError("item_code is required")
    return _ITEM_ALIASES.get(token, token)


def normalize_period_type(raw_type: str) -> str:
    token = _token(raw_type)
    period_type = _PERIOD_ALIASES.get(token, token)
    if period_type not in PERIOD_TYPES:
        raise ValueError(f"period_type must be one of {sorted(PERIOD_TYPES)}")
    return period_type


def normalize_currency(raw_currency: str | None) -> str:
    currency = (raw_currency or "VND").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter ISO code")
    return currency


def infer_period_start(
    period_end: datetime,
    period_type: str,
    fiscal_year: int,
    fiscal_quarter: int | None,
    explicit_start: datetime | None = None,
) -> datetime | None:
    """Infer a calendar start only when the fiscal boundary is unambiguous."""

    if explicit_start is not None:
        start = explicit_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        return start.astimezone(UTC)
    if period_type in {"year", "ytd"}:
        return datetime(fiscal_year, 1, 1, tzinfo=UTC)
    if period_type == "quarter" and fiscal_quarter in {1, 2, 3, 4}:
        return datetime(fiscal_year, (fiscal_quarter - 1) * 3 + 1, 1, tzinfo=UTC)
    # A TTM period cannot be reconstructed safely without the source's exact
    # fiscal calendar, so leave it null instead of inventing a boundary.
    return None


def discrete_quarter_from_ytd(current_ytd: Decimal, prior_ytd: Decimal | None) -> Decimal:
    """Convert a cumulative YTD value to a standalone quarter value."""

    if prior_ytd is None:
        return current_ytd
    return current_ytd - prior_ytd


def period_end_date(value: datetime) -> date:
    return value.date()
