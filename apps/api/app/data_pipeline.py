import importlib.util
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import Settings
from app.connectors.base import ConnectorError, DataCapability, MarketDataConnector
from app.connectors.financial import AuthorizedCsvFinancialProvider, FinancialProviderError
from app.connectors.manager import ConnectorManager
from app.connectors.ssi import SsiFastConnectConnector
from app.connectors.vnstock import VnstockConnector
from app.database import (
    DataSyncErrorRecord,
    DataSyncRunRecord,
    MarketIndexObservationRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
    SourceHealthRecord,
)
from app.market_foundation import _same_index_value
from app.normalization import normalize_price_series
from app.repositories import (
    FinancialRepository,
    PriceRepository,
    SecuritiesRepository,
    SourceHealthRepository,
)
from app.schemas import DataSyncRun, ProviderCapabilityStatus
from app.secure_http import fetch_authorized_csv, validate_https_destination


def sync_run_schema(row: DataSyncRunRecord) -> DataSyncRun:
    return DataSyncRun(
        id=row.id,
        provider=row.provider,
        capability=row.capability,
        symbol=row.symbol,
        sync_mode=row.sync_mode,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cursor_from=row.cursor_from,
        cursor_to=row.cursor_to,
        inserted_count=row.inserted_count,
        updated_count=row.updated_count,
        skipped_count=row.skipped_count,
        error_count=row.error_count,
        error_message=row.error_message,
        details=json.loads(row.details_json or "{}"),
    )


def _latest_success(provider: str) -> DataSyncRunRecord | None:
    with SessionLocal() as session:
        return session.scalar(
            select(DataSyncRunRecord)
            .where(
                DataSyncRunRecord.provider == provider,
                DataSyncRunRecord.status == "SUCCESS",
            )
            .order_by(DataSyncRunRecord.finished_at.desc())
        )


def provider_catalog(settings: Settings) -> list[ProviderCapabilityStatus]:
    with SessionLocal() as session:
        health = {
            row.source_name: row
            for row in session.scalars(select(SourceHealthRecord)).all()
        }

    def success_time(provider_id: str, health_name: str | None = None):
        run = _latest_success(provider_id)
        source = health.get(health_name or "")
        values = [
            value
            for value in (
                run.finished_at if run else None,
                source.last_success_at if source else None,
            )
            if value is not None
        ]
        return max(values) if values else None

    yahoo_success = success_time("yahoo", "Yahoo Finance chart")
    manual_success = success_time("authorized_file")
    fixture_success = success_time("fixture", "Synthetic fixture (development only)")
    market_fixture = settings.market_data_mode == "fixture"
    ssi_sdk_ready = importlib.util.find_spec("ssi_fc_data") is not None
    vnstock_ready = importlib.util.find_spec("vnstock") is not None
    vnstock_success = success_time("vnstock", "Vnstock v5")
    return [
        ProviderCapabilityStatus(
            provider_id="vnstock",
            name="Vnstock v5",
            documentation_url="https://www.vnstocks.com/docs/vnstock/thi-truong-market",
            documented_capabilities=[
                DataCapability.SECURITIES_METADATA,
                DataCapability.HISTORICAL_OHLCV,
                DataCapability.MARKET_INDICES,
            ],
            enabled_capabilities=(
                [
                    DataCapability.SECURITIES_METADATA,
                    DataCapability.HISTORICAL_OHLCV,
                    DataCapability.MARKET_INDICES,
                ]
                if vnstock_ready and not market_fixture else []
            ),
            authentication="Vnstock registration and upstream source entitlement",
            access_requirements=(
                "Install Vnstock v5 and configure a permitted upstream source; "
                "source-specific account/rights remain the operator's responsibility."
            ),
            licensing="Vnstock is a client library; upstream data terms and redistribution rights apply.",
            availability=(
                "available" if vnstock_success else "configured" if vnstock_ready and not market_fixture else "blocked"
            ),
            last_success_at=vnstock_success,
            test_result=(
                "Live Vnstock request succeeded."
                if vnstock_success
                else "Package import is ready; no successful Vnstock request has been persisted."
                if vnstock_ready
                else "BLOCKED: install optional Vnstock v5 before enabling this provider."
            ),
            cost_and_limits="Depends on the selected upstream source; no Vnstock entitlement is assumed.",
        ),
        ProviderCapabilityStatus(
            provider_id="yahoo",
            name="Yahoo Finance chart",
            documentation_url="https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html",
            documented_capabilities=[DataCapability.HISTORICAL_OHLCV],
            enabled_capabilities=(
                [] if market_fixture else [DataCapability.HISTORICAL_OHLCV]
            ),
            authentication="none",
            access_requirements="Public upstream access; commercial redistribution rights are not asserted.",
            licensing="Development connector only until production rights are verified.",
            availability=(
                "available" if yahoo_success else "blocked" if market_fixture else "configured"
            ),
            last_success_at=yahoo_success,
            last_checked_at=health.get("Yahoo Finance chart").checked_at
            if health.get("Yahoo Finance chart")
            else None,
            test_result=(
                "Real request succeeded." if yahoo_success else "No successful request persisted yet."
            ),
            cost_and_limits="No verified quota or production entitlement for this connector.",
        ),
        ProviderCapabilityStatus(
            provider_id="fixture",
            name="Synthetic fixture (development only)",
            documented_capabilities=[],
            enabled_capabilities=(
                [DataCapability.HISTORICAL_OHLCV] if market_fixture else []
            ),
            authentication="none",
            access_requirements="MARKET_DATA_MODE=fixture; never selected implicitly in production.",
            licensing="Synthetic test data, not market data.",
            availability="fixture" if market_fixture else "blocked",
            last_success_at=fixture_success,
            test_result="Deterministic test connector.",
            cost_and_limits="No external cost; maximum 520 generated observations per request.",
        ),
        ProviderCapabilityStatus(
            provider_id="authorized_file",
            name="User-authorized files",
            documentation_url=None,
            documented_capabilities=[
                DataCapability.SECURITIES_METADATA,
                DataCapability.CORPORATE_ACTIONS,
                DataCapability.INCOME_STATEMENT,
                DataCapability.BALANCE_SHEET,
                DataCapability.CASH_FLOW_STATEMENT,
            ],
            enabled_capabilities=[
                DataCapability.SECURITIES_METADATA,
                DataCapability.CORPORATE_ACTIONS,
                DataCapability.INCOME_STATEMENT,
                DataCapability.BALANCE_SHEET,
                DataCapability.CASH_FLOW_STATEMENT,
            ],
            authentication="Application admin bearer token",
            access_requirements="Operator supplies a lawful CSV/XLSX export and provenance.",
            licensing="Rights remain with the supplied source; operator confirms permitted use.",
            availability="available" if manual_success else "configured",
            last_success_at=manual_success,
            test_result=(
                "Validated import succeeded." if manual_success else "Import path is implemented and tested."
            ),
            cost_and_limits="No provider fee; request-size and admin rate limits apply.",
        ),
        ProviderCapabilityStatus(
            provider_id="fireant",
            name="FireAnt REST API v1",
            documentation_url="https://api.fireant.vn/",
            documented_capabilities=[
                DataCapability.SECURITIES_METADATA,
                DataCapability.INCOME_STATEMENT,
                DataCapability.BALANCE_SHEET,
                DataCapability.CASH_FLOW_STATEMENT,
            ],
            enabled_capabilities=[],
            authentication="OAuth2 bearer token with explicit scopes",
            access_requirements="FireAnt account, granted scopes and data entitlement.",
            licensing="Applicable FireAnt data agreement and redistribution rights required.",
            availability="configured" if settings.fireant_access_token else "blocked",
            test_result=(
                "Token configured; data scopes remain unverified."
                if settings.fireant_access_token
                else "BLOCKED: FIREANT_ACCESS_TOKEN is not configured."
            ),
            cost_and_limits="Public price and quota were not verified.",
        ),
        ProviderCapabilityStatus(
            provider_id="ssi_fastconnect",
            name="SSI FastConnect API v3",
            documentation_url="https://developers.ssi.com.vn/docs/getting-started/overview",
            documented_capabilities=[
                DataCapability.SECURITIES_METADATA,
                DataCapability.HISTORICAL_OHLCV,
                DataCapability.MARKET_INDICES,
            ],
            enabled_capabilities=(
                [
                    DataCapability.SECURITIES_METADATA,
                    DataCapability.HISTORICAL_OHLCV,
                    DataCapability.MARKET_INDICES,
                ]
                if settings.ssi_api_key and settings.ssi_api_secret and ssi_sdk_ready
                else []
            ),
            authentication="API key + secret exchanged for Bearer JWT",
            access_requirements="SSI account, FastConnect registration and approval.",
            licensing="SSI service terms and redistribution permission apply.",
            availability=(
                "configured"
                if settings.ssi_api_key and settings.ssi_api_secret
                else "blocked"
            ),
            test_result=(
                (
                    "Official SDK and credentials configured; authenticated integration test is still required."
                    if ssi_sdk_ready
                    else "Credentials configured but the official ssi-fc-data package is missing."
                )
                if settings.ssi_api_key and settings.ssi_api_secret
                else "BLOCKED: SSI_API_KEY/SSI_API_SECRET are not configured."
            ),
            cost_and_limits=(
                "Per-key rate-limit headers; daily history from listing date and intraday history for one year."
            ),
        ),
        ProviderCapabilityStatus(
            provider_id="fiingroup",
            name="FiinGroup API Datafeed",
            documentation_url="https://datafeed.fiingroup.vn/",
            documented_capabilities=list(DataCapability),
            enabled_capabilities=[],
            authentication="Commercial provider credentials",
            access_requirements="FiinGroup contract, entitlement and redistribution terms.",
            licensing="Commercial data agreement required.",
            availability=(
                "configured"
                if settings.fiingroup_api_key
                and settings.fiingroup_financial_endpoint_template
                and settings.fiingroup_rights_confirmed
                else "blocked"
            ),
            test_result=(
                "Contract endpoint and credential configured; connector remains disabled until a real call is verified."
                if settings.fiingroup_api_key
                and settings.fiingroup_financial_endpoint_template
                and settings.fiingroup_rights_confirmed
                else "BLOCKED: FiinGroup credential, endpoint, or rights confirmation is missing."
            ),
            cost_and_limits="Contact provider; public pricing was not verified.",
        ),
    ]


class DataSyncService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = ConnectorManager(settings)
        self.financial_provider = AuthorizedCsvFinancialProvider(
            settings,
            fetcher=fetch_authorized_csv,
            destination_validator=validate_https_destination,
        )

    def _provider(
        self,
        provider_id: str,
        capability: DataCapability = DataCapability.HISTORICAL_OHLCV,
    ) -> MarketDataConnector:
        candidates = [
            provider
            for provider in self.manager.providers
            if provider.supports(capability)
        ]
        if provider_id != "auto":
            candidates = [provider for provider in candidates if provider.provider_id == provider_id]
        # An explicit SSI request must not depend on the local provider priority
        # setting.  This keeps admin backfills deterministic while preserving the
        # normal priority chain for public price reads.
        if not candidates and provider_id == "ssi_fastconnect":
            candidate = SsiFastConnectConnector(self.settings)
            if candidate.supports(capability):
                candidates = [candidate]
        if not candidates and provider_id == "vnstock":
            candidate = VnstockConnector(self.settings)
            if candidate.supports(capability):
                candidates = [candidate]
        if not candidates:
            raise ValueError(
                f"Provider {provider_id} không được bật cho capability {capability}."
            )
        return candidates[0]

    @staticmethod
    def _start(
        provider: str,
        capability: DataCapability,
        symbol: str | None,
        sync_mode: str,
        cursor_from: datetime | None,
    ) -> int:
        with SessionLocal() as session:
            row = DataSyncRunRecord(
                provider=provider,
                capability=capability,
                symbol=symbol,
                sync_mode=sync_mode,
                status="RUNNING",
                started_at=datetime.now(UTC),
                cursor_from=cursor_from,
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                error_count=0,
                details_json="{}",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id

    @staticmethod
    def _blocked(symbol: str, message: str) -> DataSyncRun:
        run_id = DataSyncService._start(
            "none",
            DataCapability.INCOME_STATEMENT,
            symbol,
            "incremental",
            None,
        )
        with SessionLocal() as session:
            row = session.get(DataSyncRunRecord, run_id)
            row.status = "BLOCKED"
            row.finished_at = datetime.now(UTC)
            row.error_count = 1
            row.error_message = message
            session.add(
                DataSyncErrorRecord(
                    run_id=run_id,
                    symbol=symbol,
                    error_code="provider_unavailable",
                    message=message,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
            session.refresh(row)
            return sync_run_schema(row)

    async def sync_prices(
        self,
        symbol: str,
        *,
        provider_id: str = "auto",
        requested_mode: str = "auto",
        limit: int = 520,
    ) -> DataSyncRun:
        symbol = symbol.strip().upper()
        provider = self._provider(provider_id)
        with SessionLocal() as session:
            security = session.scalar(
                select(SecurityRecord).where(SecurityRecord.symbol == symbol)
            )
            if security is None:
                raise ValueError(f"Mã {symbol} chưa có trong securities master.")
            latest = session.scalar(
                select(func.max(PriceObservation.market_timestamp)).where(
                    PriceObservation.security_id == security.id,
                    PriceObservation.provider == provider.name,
                    PriceObservation.interval == "1d",
                )
            )
        sync_mode = (
            "initial"
            if requested_mode == "initial" or latest is None
            else "incremental"
        )
        cursor = latest if sync_mode == "incremental" else None
        run_id = self._start(
            provider.provider_id,
            DataCapability.HISTORICAL_OHLCV,
            symbol,
            sync_mode,
            cursor,
        )
        try:
            series = normalize_price_series(
                await provider.prices_since(symbol, cursor, limit),
                allow_empty=cursor is not None,
            )
            with SessionLocal() as session:
                counts = PriceRepository(session).upsert_series_with_counts(series)
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "SUCCESS"
                row.finished_at = datetime.now(UTC)
                row.cursor_to = series.bars[-1].timestamp if series.bars else cursor
                row.inserted_count = counts.inserted
                row.updated_count = counts.updated
                row.skipped_count = counts.skipped
                row.details_json = json.dumps(
                    {
                        "source_name": series.provenance.source,
                        "source_url": series.provenance.source_url,
                        "retrieved_at": series.provenance.retrieved_at.isoformat(),
                        "market_timestamp": series.provenance.market_timestamp.isoformat()
                        if series.provenance.market_timestamp
                        else None,
                        "validation_status": series.provenance.validation_status,
                        "source_mode": series.provenance.mode,
                    }
                )
                SourceHealthRepository(session).record(
                    provider.name, status="available", message="price sync succeeded"
                )
                session.commit()
                session.refresh(row)
                return sync_run_schema(row)
        except (ConnectorError, ValueError) as exc:
            with SessionLocal() as session:
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "FAILED"
                row.finished_at = datetime.now(UTC)
                row.error_count = 1
                row.error_message = str(exc)[:1024]
                session.add(
                    DataSyncErrorRecord(
                        run_id=run_id,
                        symbol=symbol,
                        error_code="provider_error",
                        message=str(exc)[:1024],
                        created_at=datetime.now(UTC),
                    )
                )
                SourceHealthRepository(session).record(
                    provider.name, status="unavailable", message=str(exc)[:512]
                )
                session.commit()
            raise ConnectorError(str(exc)) from exc

    async def sync_securities(
        self,
        *,
        provider_id: str = "vnstock",
        markets: tuple[str, ...] = ("HOSE", "HNX", "UPCOM"),
    ) -> DataSyncRun:
        """Backfill the securities master from an authorized provider.

        The provider owns the source and entitlement check.  CSV/XLSX importers
        remain independent and are not routed through this method.
        """
        provider = self._provider(provider_id, DataCapability.SECURITIES_METADATA)
        run_id = self._start(
            provider.provider_id,
            DataCapability.SECURITIES_METADATA,
            None,
            "initial",
            None,
        )
        try:
            securities = await provider.securities_metadata(markets)
            inserted = updated = 0
            with SessionLocal() as session:
                repository = SecuritiesRepository(session)
                for security in securities:
                    _, was_inserted = repository.upsert(security)
                    inserted += int(was_inserted)
                    updated += int(not was_inserted)
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "SUCCESS"
                row.finished_at = datetime.now(UTC)
                row.inserted_count = inserted
                row.updated_count = updated
                row.details_json = json.dumps(
                    {
                        "markets": list(markets),
                        "records": len(securities),
                        "source_mode": "live",
                    }
                )
                SourceHealthRepository(session).record(
                    provider.name,
                    status="available",
                    message="securities metadata sync succeeded",
                )
                session.commit()
                session.refresh(row)
                return sync_run_schema(row)
        except (ConnectorError, ValueError) as exc:
            with SessionLocal() as session:
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "BLOCKED" if str(exc).startswith("BLOCKED") else "FAILED"
                row.finished_at = datetime.now(UTC)
                row.error_count = 1
                row.error_message = str(exc)[:1024]
                session.add(
                    DataSyncErrorRecord(
                        run_id=run_id,
                        symbol=None,
                        error_code="provider_error",
                        message=str(exc)[:1024],
                        created_at=datetime.now(UTC),
                    )
                )
                SourceHealthRepository(session).record(
                    provider.name,
                    status="unavailable",
                    message=str(exc)[:512],
                )
                session.commit()
            raise ConnectorError(str(exc)) from exc

    async def sync_indices(self, *, provider_id: str = "vnstock") -> DataSyncRun:
        """Backfill official index observations without deriving an index from stocks."""
        provider = self._provider(provider_id, DataCapability.MARKET_INDICES)
        run_id = self._start(
            provider.provider_id,
            DataCapability.MARKET_INDICES,
            None,
            "initial",
            None,
        )
        try:
            observations = await provider.market_indices()
            inserted = updated = skipped = 0
            with SessionLocal() as session:
                for observation in observations:
                    existing = session.scalar(
                        select(MarketIndexObservationRecord).where(
                            MarketIndexObservationRecord.symbol == observation["symbol"],
                            MarketIndexObservationRecord.provider_id
                            == observation["provider_id"],
                            MarketIndexObservationRecord.market_session_date
                            == observation["market_session_date"],
                        )
                    )
                    values = {
                        **observation,
                        "close": observation["close"],
                    }
                    if existing is None:
                        session.add(MarketIndexObservationRecord(**values))
                        inserted += 1
                    elif all(
                        _same_index_value(getattr(existing, key), value)
                        for key, value in values.items()
                        if key not in {"last_updated"}
                    ):
                        skipped += 1
                    else:
                        for key, value in values.items():
                            setattr(existing, key, value)
                        updated += 1
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "SUCCESS"
                row.finished_at = datetime.now(UTC)
                row.inserted_count = inserted
                row.updated_count = updated
                row.skipped_count = skipped
                row.details_json = json.dumps(
                    {"records": len(observations), "source_mode": "live"}
                )
                SourceHealthRepository(session).record(
                    provider.name,
                    status="available",
                    message="market index sync succeeded",
                )
                session.commit()
                session.refresh(row)
                return sync_run_schema(row)
        except (ConnectorError, ValueError, TypeError) as exc:
            with SessionLocal() as session:
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "BLOCKED" if str(exc).startswith("BLOCKED") else "FAILED"
                row.finished_at = datetime.now(UTC)
                row.error_count = 1
                row.error_message = str(exc)[:1024]
                session.add(
                    DataSyncErrorRecord(
                        run_id=run_id,
                        symbol=None,
                        error_code="provider_error",
                        message=str(exc)[:1024],
                        created_at=datetime.now(UTC),
                    )
                )
                SourceHealthRepository(session).record(
                    provider.name,
                    status="unavailable",
                    message=str(exc)[:512],
                )
                session.commit()
            raise ConnectorError(str(exc)) from exc

    def sync_financials(self, symbol: str) -> DataSyncRun:
        """Import an explicitly licensed HTTPS CSV feed; never infer API access."""
        symbol = symbol.strip().upper()
        with SessionLocal() as session:
            exists = session.scalar(
                select(SecurityRecord.id).where(SecurityRecord.symbol == symbol)
            )
        if exists is None:
            raise ValueError(f"Mã {symbol} chưa có trong securities master.")

        try:
            result = self.financial_provider.fetch(symbol)
        except FinancialProviderError as exc:
            return self._blocked(symbol, str(exc))
        run_id = self._start(
            result.provider_id,
            DataCapability.INCOME_STATEMENT,
            symbol,
            "incremental",
            None,
        )
        try:
            with SessionLocal() as session:
                imported = FinancialRepository(session).import_csv(
                    symbol,
                    result.content,
                    result.provider_id,
                    strict=True,
                    accept_verified_status=False,
                )
            with SessionLocal() as session:
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "FAILED" if imported.rejected else "SUCCESS"
                row.inserted_count = imported.inserted_items
                row.updated_count = imported.updated_items
                row.skipped_count = imported.skipped_items
                row.error_count = imported.rejected
                row.error_message = (
                    "; ".join(imported.errors)[:1024] if imported.errors else None
                )
                row.finished_at = datetime.now(UTC)
                row.details_json = json.dumps(
                    {
                        "source_host": result.source_host,
                        "retrieved_at": result.retrieved_at.isoformat(),
                        "inserted_periods": imported.inserted_periods,
                        "updated_periods": imported.updated_periods,
                        "validation_statuses": sorted(
                            {report.validation_status for report in imported.validation_reports}
                        ),
                        "status": row.status,
                    }
                )
                SourceHealthRepository(session).record(
                    result.provider_id,
                    status="available" if not imported.rejected else "unavailable",
                    message="financial statement CSV sync completed",
                )
                session.commit()
                session.refresh(row)
                return sync_run_schema(row)
        except (FinancialProviderError, ValueError) as exc:
            # Do not log tokens, response bodies or request URLs containing secrets.
            message = f"Authorized financial CSV sync failed: {type(exc).__name__}"
            with SessionLocal() as session:
                row = session.get(DataSyncRunRecord, run_id)
                row.status = "FAILED"
                row.finished_at = datetime.now(UTC)
                row.error_count = 1
                row.error_message = message
                session.add(
                    DataSyncErrorRecord(
                        run_id=run_id, symbol=symbol, error_code="provider_error",
                        message=message, created_at=datetime.now(UTC),
                    )
                )
                SourceHealthRepository(session).record(
                    result.provider_id, status="unavailable", message=message
                )
                session.commit()
                session.refresh(row)
                return sync_run_schema(row)


def list_sync_runs(
    *,
    symbol: str | None = None,
    provider: str | None = None,
    capability: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[DataSyncRun]:
    statement = select(DataSyncRunRecord)
    if symbol:
        statement = statement.where(DataSyncRunRecord.symbol == symbol.strip().upper())
    if provider:
        statement = statement.where(DataSyncRunRecord.provider == provider)
    if capability:
        statement = statement.where(DataSyncRunRecord.capability == capability)
    if status:
        statement = statement.where(DataSyncRunRecord.status == status)
    with SessionLocal() as session:
        rows = session.scalars(
            statement.order_by(DataSyncRunRecord.started_at.desc()).limit(limit)
        ).all()
    return [sync_run_schema(row) for row in rows]


def record_file_import(
    *,
    capability: DataCapability,
    symbol: str | None,
    inserted: int,
    updated: int,
    skipped: int,
    rejected: int,
    source_name: str,
) -> DataSyncRun:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        row = DataSyncRunRecord(
            provider="authorized_file",
            capability=capability,
            symbol=symbol.upper() if symbol else None,
            sync_mode="incremental",
            status="PARTIAL" if rejected else "SUCCESS",
            started_at=now,
            finished_at=now,
            inserted_count=inserted,
            updated_count=updated,
            skipped_count=skipped,
            error_count=rejected,
            error_message=(f"{rejected} row(s) rejected" if rejected else None),
            details_json=json.dumps({"source_name": source_name}),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return sync_run_schema(row)
