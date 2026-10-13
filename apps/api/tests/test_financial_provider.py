import pytest

from app.config import Settings
from app.connectors.base import DataCapability
from app.connectors.financial import (
    AuthorizedCsvFinancialProvider,
    FinancialProviderError,
)


def test_authorized_csv_provider_exposes_only_declared_statement_capabilities():
    settings = Settings(
        financial_csv_url_template="https://licensed.example/{symbol}.csv",
        financial_csv_allowed_hosts="licensed.example",
        financial_csv_rights_confirmed=True,
    )
    provider = AuthorizedCsvFinancialProvider(
        settings,
        fetcher=lambda *args, **kwargs: "period_end,period_type,fiscal_year,statement_type,item_code,value\n",
        destination_validator=lambda url, allowed_hosts: "licensed.example",
    )

    assert provider.capabilities == frozenset(
        {
            DataCapability.INCOME_STATEMENT,
            DataCapability.BALANCE_SHEET,
            DataCapability.CASH_FLOW_STATEMENT,
        }
    )
    result = provider.fetch(" hpg ")
    assert result.provider_id == "authorized_https_csv"
    assert result.source_host == "licensed.example"
    assert result.retrieved_at is not None


def test_authorized_csv_provider_blocks_without_rights_before_fetch():
    called = False

    def unexpected_fetch(*args, **kwargs):
        nonlocal called
        called = True
        return ""

    provider = AuthorizedCsvFinancialProvider(
        Settings(financial_csv_url_template="https://licensed.example/{symbol}.csv"),
        fetcher=unexpected_fetch,
    )

    with pytest.raises(FinancialProviderError, match="BLOCKED"):
        provider.fetch("HPG")
    assert called is False
