"""Capability and provenance audit for the data-first platform.

This module is intentionally read-only.  A persisted row is not treated as
proof of a live, licensed feed: the response keeps record coverage, provider
verification, and licensing/rights status separate.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import Settings
from app.data_pipeline import provider_catalog
from app.database import (
    CorporateActionRecord,
    DataSyncRunRecord,
    FinancialPeriodRecord,
    MarketIndexObservationRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
)

IMPLEMENTED_AND_LIVE_VERIFIED = "IMPLEMENTED_AND_LIVE_VERIFIED"
IMPLEMENTED_FILE_VERIFIED = "IMPLEMENTED_FILE_VERIFIED"
IMPLEMENTED_MOCK_TESTED = "IMPLEMENTED_MOCK_TESTED"
CONFIGURED_NOT_VERIFIED = "CONFIGURED_NOT_VERIFIED"
BLOCKED_EXTERNAL_DEPENDENCY = "BLOCKED_EXTERNAL_DEPENDENCY"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


def _status_from_run(provider: str | None) -> str:
    if provider == "fixture":
        return IMPLEMENTED_MOCK_TESTED
    if provider == "authorized_file" or provider == "bootstrap-manual":
        return IMPLEMENTED_FILE_VERIFIED
    return IMPLEMENTED_AND_LIVE_VERIFIED


def build_capability_audit(settings: Settings) -> dict:
    """Return an evidence-backed capability matrix without contacting providers."""

    now = datetime.now(UTC)
    with SessionLocal() as session:
        security_count = session.scalar(select(func.count(SecurityRecord.id))) or 0
        security_symbols = session.scalar(
            select(func.count(func.distinct(SecurityRecord.symbol)))
        ) or 0
        price_count = session.scalar(select(func.count(PriceObservation.id))) or 0
        price_symbols = session.scalar(
            select(func.count(func.distinct(PriceObservation.security_id)))
        ) or 0
        price_sessions = session.scalar(
            select(func.count(func.distinct(PriceObservation.market_session_date)))
        ) or 0
        index_count = session.scalar(
            select(func.count(MarketIndexObservationRecord.id))
        ) or 0
        index_sessions = session.scalar(
            select(func.count(func.distinct(MarketIndexObservationRecord.market_session_date)))
        ) or 0
        financial_count = session.scalar(
            select(func.count(FinancialPeriodRecord.id))
        ) or 0
        financial_symbols = session.scalar(
            select(func.count(func.distinct(FinancialPeriodRecord.security_id)))
        ) or 0
        action_count = session.scalar(select(func.count(CorporateActionRecord.id))) or 0
        securities_last_update = session.scalar(select(func.max(SecurityRecord.last_updated)))
        price_last_update = session.scalar(select(func.max(PriceObservation.ingested_at)))
        index_last_update = session.scalar(select(func.max(MarketIndexObservationRecord.retrieved_at)))
        financial_last_update = session.scalar(select(func.max(FinancialPeriodRecord.retrieved_at)))
        action_last_update = session.scalar(select(func.max(CorporateActionRecord.retrieved_at)))
        price_modes = {
            value
            for value in session.scalars(select(PriceObservation.source_mode).distinct()).all()
            if value
        }
        runs = list(
            session.scalars(
                select(DataSyncRunRecord)
                .where(DataSyncRunRecord.status == "SUCCESS")
                .order_by(DataSyncRunRecord.finished_at.desc())
            ).all()
        )

    latest_by_capability: dict[str, DataSyncRunRecord] = {}
    for run in runs:
        latest_by_capability.setdefault(run.capability, run)

    catalog = provider_catalog(settings)
    providers = [item.model_dump(mode="json") for item in catalog]
    provider_by_id = {item.provider_id: item for item in catalog}

    def configured_provider(capability: str) -> str | None:
        for provider_id, item in provider_by_id.items():
            if (capability in item.enabled_capabilities or capability in item.documented_capabilities) and item.availability in {"configured", "available", "fixture"}:
                return provider_id
        return None

    def capability(
        capability_id: str,
        dataset: str,
        records: int,
        symbols: int | None,
        sessions: int | None,
        run_keys: tuple[str, ...],
        provider_ids: tuple[str, ...],
        *,
        last_update=None,
        observed_modes: set[str] | None = None,
        rights: str = "not_verified",
        blocker: str | None = None,
    ) -> dict:
        run = next(
            (latest_by_capability[key] for key in run_keys if key in latest_by_capability),
            None,
        )
        persisted_provider = run.provider if run else None
        source_provider = persisted_provider or configured_provider(capability_id)
        if dataset == "securities" and records and not run:
            source_provider = "bootstrap-manual"
        if run:
            status = _status_from_run(persisted_provider)
            evidence = "successful sync run persisted"
        elif records:
            # Existing bootstrap/fixture rows are evidence of implementation, not a
            # claim that an authorized live feed is connected.
            source_values = {
                value
                for value in (
                    "bootstrap-manual" if dataset == "securities" else None,
                    settings.market_data_mode if dataset in {"ohlcv", "indices"} else None,
                )
                if value
            }
            if observed_modes and "live" in observed_modes:
                status = IMPLEMENTED_AND_LIVE_VERIFIED
                evidence = "live-mode observations persisted with provider provenance"
            elif observed_modes and "fixture" in observed_modes:
                status = IMPLEMENTED_MOCK_TESTED
                evidence = "fixture rows persisted"
            elif observed_modes and "authorized" in observed_modes:
                status = IMPLEMENTED_FILE_VERIFIED
                evidence = "authorized file rows persisted"
            elif dataset == "securities" and "bootstrap-manual" in source_values:
                status = IMPLEMENTED_FILE_VERIFIED
                evidence = "bootstrap file schema validated and persisted"
            else:
                status = IMPLEMENTED_FILE_VERIFIED
                evidence = "persisted rows; source verification is limited to stored provenance"
        elif source_provider == "fixture":
            status = IMPLEMENTED_MOCK_TESTED
            evidence = "deterministic fixture connector is available; no fixture rows are persisted yet"
        elif source_provider:
            status = CONFIGURED_NOT_VERIFIED
            evidence = "provider is configured or documented, but no successful run is persisted"
        elif blocker:
            status = BLOCKED_EXTERNAL_DEPENDENCY
            evidence = "external provider, credentials, or rights are required"
        else:
            status = NOT_IMPLEMENTED
            evidence = "no persisted dataset or configured provider"
        if source_provider in {"vnstock", "ssi_fastconnect", "fiingroup", "fireant"} and not run:
            status = CONFIGURED_NOT_VERIFIED if source_provider in provider_by_id and provider_by_id[source_provider].availability == "configured" else BLOCKED_EXTERNAL_DEPENDENCY
        return {
            "capability": capability_id,
            "dataset": dataset,
            "status": status,
            "provider": source_provider,
            "provider_candidates": list(provider_ids),
            "records": records,
            "symbols": symbols,
            "sessions": sessions,
            "last_update": last_update,
            "successful_sync_id": run.id if run else None,
            "successful_sync_at": run.finished_at if run else None,
            "verification": "request_success" if status == IMPLEMENTED_AND_LIVE_VERIFIED else "schema_or_fixture_only" if status in {IMPLEMENTED_FILE_VERIFIED, IMPLEMENTED_MOCK_TESTED} else "not_verified",
            "license_rights": rights,
            "evidence": evidence,
            "blocker": blocker if status in {BLOCKED_EXTERNAL_DEPENDENCY, CONFIGURED_NOT_VERIFIED} else None,
        }

    capabilities = [
        capability(
            "securities_metadata", "securities", security_count, security_symbols, None,
            ("securities_metadata", "securities"), ("authorized_file", "vnstock", "ssi_fastconnect", "fireant"),
            last_update=securities_last_update,
            rights="operator-supplied source rights not independently verified",
            blocker="Authorized securities master or provider entitlement is required for full-market coverage.",
        ),
        capability(
            "historical_ohlcv", "ohlcv", price_count, price_symbols, price_sessions,
            ("historical_ohlcv", "prices"), ("vnstock", "yahoo", "ssi_fastconnect", "authorized_file"),
            last_update=price_last_update,
            observed_modes=price_modes,
            rights="Yahoo development terms or authorized provider agreement required",
            blocker="No authorized production provider has a persisted successful run.",
        ),
        capability(
            "market_indices", "indices", index_count, None, index_sessions,
            ("market_indices", "indices"), ("vnstock", "ssi_fastconnect", "authorized_file"),
            last_update=index_last_update,
            rights="official exchange/provider rights not verified",
            blocker="Official VN-Index/VN30/HNX/UPCoM feed or authorized import is required.",
        ),
        capability(
            "financial_statements", "financials", financial_count, financial_symbols, None,
            ("financial_statements", "financials", "income_statement"), ("fiingroup", "authorized_file"),
            last_update=financial_last_update,
            rights="FiinGroup contract or lawful issuer export required",
            blocker="FiinGroup API rights/contract are not verified; CSV import remains the supported fallback.",
        ),
        capability(
            "corporate_actions", "corporate_actions", action_count, None, None,
            ("corporate_actions",), ("authorized_file", "ssi_fastconnect"),
            last_update=action_last_update,
            rights="source rights not verified",
            blocker="No authorized corporate-action provider run is persisted.",
        ),
        capability(
            "market_cap", "market_cap", 0, None, None,
            ("historical_ohlcv", "prices"), ("ssi_fastconnect", "authorized_file"),
            last_update=price_last_update,
            rights="depends on authorized price/universe source",
            blocker="Market cap is only available on observations that carry a provider-supplied value.",
        ),
        capability(
            "trading_value", "trading_value", 0, None, None,
            ("historical_ohlcv", "prices"), ("ssi_fastconnect", "authorized_file"),
            last_update=price_last_update,
            rights="depends on authorized price source",
            blocker="Actual trading value is not inferred from close × volume.",
        ),
        capability(
            "foreign_flow", "foreign_flow", 0, None, None,
            ("foreign_flow",), ("ssi_fastconnect", "authorized_file"),
            rights="provider entitlement required",
            blocker="No persisted foreign-flow table/provider is available.",
        ),
    ]
    # Populate derived OHLCV fields without inventing values.  Each row remains
    # explicitly marked as unavailable when the corresponding column is empty.
    with SessionLocal() as session:
        market_cap_records = session.scalar(
            select(func.count(PriceObservation.id)).where(PriceObservation.market_cap.is_not(None))
        ) or 0
        trading_value_records = session.scalar(
            select(func.count(PriceObservation.id)).where(PriceObservation.actual_trading_value.is_not(None))
        ) or 0
        for row in capabilities:
            if row["capability"] == "market_cap":
                row["records"] = market_cap_records
            elif row["capability"] == "trading_value":
                row["records"] = trading_value_records
            if row["capability"] in {"market_cap", "trading_value"} and row["records"]:
                source = next(item for item in capabilities if item["capability"] == "historical_ohlcv")
                if source["status"] in {
                    IMPLEMENTED_AND_LIVE_VERIFIED,
                    IMPLEMENTED_FILE_VERIFIED,
                    IMPLEMENTED_MOCK_TESTED,
                }:
                    row["status"] = source["status"]
                    row["provider"] = source["provider"]
                    row["verification"] = source["verification"]
                    row["evidence"] = "provider-supplied values persisted on OHLCV observations"

    return {
        "generated_at": now,
        "market_data_mode": settings.market_data_mode,
        "status_definitions": {
            IMPLEMENTED_AND_LIVE_VERIFIED: "A real authorized request succeeded and its sync run is persisted.",
            IMPLEMENTED_FILE_VERIFIED: "A supplied file/import was schema-validated and persisted; it is not automatically live.",
            IMPLEMENTED_MOCK_TESTED: "Only labelled fixture data has been exercised.",
            CONFIGURED_NOT_VERIFIED: "Configuration exists, but no successful authorized request is persisted.",
            BLOCKED_EXTERNAL_DEPENDENCY: "Credentials, provider contract, source rights, or official calendar are missing.",
            NOT_IMPLEMENTED: "No persisted dataset or implementation evidence is available.",
        },
        "capabilities": capabilities,
        "providers": providers,
        "limitations": [
            "Row counts never imply full-market or realtime coverage.",
            "Fixture and file imports retain provenance and are not promoted to live status.",
            "Licensing and redistribution rights require an operator/provider confirmation.",
        ],
    }
