import pytest

from app.config import Settings
from app.connectors.financial import FiinGroupFinancialProvider, FinancialProviderError


def test_fiin_group_provider_blocks_without_contract_and_rights():
    provider = FiinGroupFinancialProvider(Settings(fiingroup_api_key=None))
    with pytest.raises(FinancialProviderError, match="BLOCKED"):
        provider.fetch("HPG")


def test_fiin_group_provider_uses_only_explicit_contract_endpoint():
    calls = []

    def fetcher(url: str, key: str) -> str:
        calls.append((url, key))
        return '{"ticker":"HPG"}'

    settings = Settings(
        fiingroup_api_key="test-key",
        fiingroup_financial_endpoint_template="https://licensed.fiingroup.test/report/{symbol}",
        fiingroup_rights_confirmed=True,
    )
    result = FiinGroupFinancialProvider(settings, fetcher=fetcher).fetch("hpg")
    assert result.provider_id == "fiingroup"
    assert calls == [("https://licensed.fiingroup.test/report/HPG", "test-key")]
