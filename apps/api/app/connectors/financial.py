"""Explicit financial-statement provider boundary.

Only the authorized CSV provider is implemented in this repository. Licensed
API providers can implement the same contract later without making the sync
service guess undocumented endpoints.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.connectors.base import DataCapability
from app.secure_http import SecureFetchError, fetch_authorized_csv, validate_https_destination


class FinancialProviderError(RuntimeError):
    """A safe, provider-neutral financial source error."""


@dataclass(frozen=True)
class FinancialFetchResult:
    provider_id: str
    source_name: str
    source_host: str
    content: str
    retrieved_at: datetime


class FinancialStatementProvider(ABC):
    provider_id: str
    name: str
    capabilities: frozenset[DataCapability] = frozenset(
        {
            DataCapability.INCOME_STATEMENT,
            DataCapability.BALANCE_SHEET,
            DataCapability.CASH_FLOW_STATEMENT,
        }
    )

    @abstractmethod
    def fetch(self, symbol: str) -> FinancialFetchResult:
        """Fetch one symbol using a documented, authorized source."""


class AuthorizedCsvFinancialProvider(FinancialStatementProvider):
    """Fetch a user-authorized HTTPS CSV without inferring provider endpoints."""

    provider_id = "authorized_https_csv"
    name = "Authorized financial CSV"

    def __init__(
        self,
        settings: Settings,
        *,
        fetcher: Callable[..., str] = fetch_authorized_csv,
        destination_validator: Callable[[str, set[str]], str] = validate_https_destination,
    ) -> None:
        self.settings = settings
        self.fetcher = fetcher
        self.destination_validator = destination_validator

    def fetch(self, symbol: str) -> FinancialFetchResult:
        normalized_symbol = symbol.strip().upper()
        template = self.settings.financial_csv_url_template
        if not template or not self.settings.financial_csv_rights_confirmed:
            raise FinancialProviderError(
                "BLOCKED: configure FINANCIAL_CSV_URL_TEMPLATE and confirm lawful "
                "automated-use rights via FINANCIAL_CSV_RIGHTS_CONFIRMED=true."
            )
        if template.count("{symbol}") != 1:
            raise FinancialProviderError(
                "BLOCKED: URL template must contain {symbol} exactly once."
            )
        url = template.replace("{symbol}", normalized_symbol)
        allowed_hosts = {
            host.strip().rstrip(".").lower()
            for host in self.settings.financial_csv_allowed_hosts.split(",")
            if host.strip()
        }
        try:
            source_host = self.destination_validator(url, allowed_hosts)
            payload = self.fetcher(
                url,
                allowed_hosts=allowed_hosts,
                bearer_token=self.settings.financial_csv_bearer_token,
                timeout_seconds=self.settings.request_timeout_seconds,
                max_bytes=min(
                    self.settings.financial_csv_max_bytes,
                    self.settings.max_request_bytes,
                ),
                retries=self.settings.financial_csv_retries,
            )
        except SecureFetchError as exc:
            raise FinancialProviderError(f"BLOCKED: {exc}") from exc
        except ValueError as exc:
            raise FinancialProviderError(f"financial source rejected: {exc}") from exc
        return FinancialFetchResult(
            provider_id=self.provider_id,
            source_name=self.name,
            source_host=source_host,
            content=payload,
            retrieved_at=datetime.now(UTC),
        )
