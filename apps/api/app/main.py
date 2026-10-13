import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from io import BytesIO

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analyst import AnalystService
from app.analytics.fundamental import calculate_financial_metrics
from app.analytics.valuation import (
    calculate_dcf_sensitivity,
    calculate_dcf_valuation,
    calculate_relative_valuation,
)
from app.auth import Principal, audit_event, audit_success, enforce_llm_rate_limit, require_admin
from app.automation import (
    AutomationService,
    add_watchlist_item,
    create_alert_rule,
    create_watchlist,
    job_schema,
)
from app.config import Settings, get_settings
from app.connectors.base import ConnectorError, DataCapability
from app.connectors.fireant import FireAntConnector
from app.corporate_actions import import_corporate_actions, list_corporate_actions
from app.data_pipeline import (
    DataSyncService,
    list_sync_runs,
    provider_catalog,
    record_file_import,
)
from app.database import (
    DataSyncErrorRecord,
    DataSyncRunRecord,
    FinancialPeriodRecord,
    JobRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
    SourceHealthRecord,
    ValuationResultRecord,
    init_db,
)
from app.market_reporting import (
    build_market_overview,
    create_daily_market_report,
    list_report_snapshots,
)
from app.middleware import RequestBodyLimitMiddleware
from app.portfolio import (
    add_transaction,
    create_portfolio,
    import_transactions_csv,
    portfolio_summary,
)
from app.registry import import_securities_csv, import_securities_xlsx, seed_registry_if_empty
from app.reporting import build_pdf
from app.repositories import FinancialRepository, NewsRepository, SecuritiesRepository
from app.schemas import (
    AlertRuleRequest,
    AnalysisResponse,
    AnalystRequest,
    AnalystResponse,
    CorporateAction,
    CorporateActionImportResult,
    DailyMarketReport,
    DataQualityReport,
    DataSyncRun,
    DCFRequest,
    DCFSensitivityRequest,
    DCFSensitivityResult,
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementImportResult,
    FinancialStatementsResponse,
    FinancialTrendResponse,
    FinancialValidationReport,
    JobRequest,
    JobResult,
    MarketOverview,
    PortfolioCreate,
    PortfolioImportResult,
    PortfolioSummary,
    PortfolioTransactionInput,
    PriceSeries,
    ProviderCapabilityStatus,
    SecuritiesExplorerResponse,
    SecuritiesImportResult,
    Security,
    SocialBatchRequest,
    SocialBatchResult,
    SourceDiagnostic,
    SourceStatus,
    TechnicalSnapshot,
    ValuationRequest,
    ValuationResult,
    WatchlistItemRequest,
    WatchlistRequest,
)
from app.securities_explorer import list_securities
from app.services import AnalysisService
from app.social import analyze_social_batch


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_registry_if_empty()
    yield


settings = get_settings()
production_docs = settings.app_environment.lower() not in {"production", "prod"}
app = FastAPI(
    title="Mạch Thị Trường API",
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs" if production_docs else None,
    redoc_url="/redoc" if production_docs else None,
    openapi_url="/openapi.json" if production_docs else None,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(",") if host.strip()],
)


app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def service(config: Settings = Depends(get_settings)) -> AnalysisService:
    return AnalysisService(config)


@app.get("/api/v1/health")
def health(config: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"status": "ok", "market_data_mode": config.market_data_mode, "version": app.version}


@app.get("/api/v1/sources", response_model=list[SourceStatus])
def sources(config: Settings = Depends(get_settings)) -> list[SourceStatus]:
    market_source = (
        SourceStatus(
            name="Synthetic fixture (development only)",
            capabilities=["search", "historical_prices"],
            authentication="none",
            availability="fixture",
            freshness="static deterministic series",
            licensing="Development fixture; not market data.",
            message="Chỉ dùng kiểm thử; không phải dữ liệu thị trường.",
        )
        if config.market_data_mode == "fixture"
        else SourceStatus(
            name="Yahoo Finance chart",
            capabilities=["search", "historical_prices"],
            authentication="none",
            availability="configured",
            freshness="daily/delayed",
            licensing="Development connector; verify commercial redistribution rights.",
        )
    )
    return [
        market_source,
        *[
            SourceStatus(name=("VnExpress RSS" if url == "https://vnexpress.net/rss/kinh-doanh.rss" else url), capabilities=["news_metadata"], authentication="none", availability="configured", freshness="RSS publication schedule", licensing="Metadata and links only.")
            for url in config.news_feeds.split(",") if url.strip()
        ],
        SourceStatus(
            name="FireAnt",
            capabilities=["service_status"],
            authentication="OAuth2 bearer token required",
            availability="configured" if config.fireant_access_token else "unavailable",
            freshness="checked on demand at /sources/status",
            licensing="Data capabilities require verified entitlement and scopes.",
        ),
        SourceStatus(
            name="VPS SmartOne",
            capabilities=["planned_read_only_portfolio"],
            authentication="official only",
            availability="unavailable",
            freshness="unknown",
            licensing="No supported API verified.",
        ),
    ]


@app.get("/api/v1/providers", response_model=list[ProviderCapabilityStatus])
def providers(config: Settings = Depends(get_settings)) -> list[ProviderCapabilityStatus]:
    return provider_catalog(config)


@app.get("/api/v1/sources/status", response_model=list[SourceStatus])
async def source_status(config: Settings = Depends(get_settings)) -> list[SourceStatus]:
    static = sources(config)
    fireant = await FireAntConnector(
        config.fireant_base_url, config.fireant_access_token, config.request_timeout_seconds
    ).status()
    return [item for item in static if item.name != "FireAnt"] + [fireant]


@app.get("/api/v1/data-quality", response_model=DataQualityReport)
def data_quality(config: Settings = Depends(get_settings)) -> DataQualityReport:
    """Expose persisted source health and coverage without implying live connectivity."""
    with SessionLocal() as session:
        securities = list(session.scalars(select(SecurityRecord)).all())
        active_securities = [row for row in securities if row.listing_status == "active"]
        securities_count = len(securities)
        active_securities_count = len(active_securities)
        exchange_distribution = {
            exchange: count
            for exchange, count in session.execute(
                select(SecurityRecord.exchange, func.count(SecurityRecord.id))
                .where(SecurityRecord.listing_status == "active")
                .group_by(SecurityRecord.exchange)
            )
        }
        security_ids_with_prices = set(
            session.scalars(select(PriceObservation.security_id).distinct()).all()
        )
        active_with_prices = [
            row for row in active_securities if row.id in security_ids_with_prices
        ]
        missing_price_symbols = sorted(
            row.symbol for row in active_securities if row.id not in security_ids_with_prices
        )
        security_ids_with_financials = set(
            session.scalars(select(FinancialPeriodRecord.security_id).distinct()).all()
        )
        active_with_financials = [
            row for row in active_securities if row.id in security_ids_with_financials
        ]
        missing_financial_symbols = sorted(
            row.symbol
            for row in active_securities
            if row.id not in security_ids_with_financials
        )
        sync_error_records = session.scalar(select(func.count(DataSyncErrorRecord.id))) or 0
        failed_sync_symbols = sorted(
            symbol
            for symbol in session.scalars(
                select(DataSyncRunRecord.symbol)
                .where(
                    DataSyncRunRecord.status.in_(["FAILED", "BLOCKED"]),
                    DataSyncRunRecord.symbol.is_not(None),
                )
                .distinct()
            )
            if symbol
        )
        price_observations_count = session.scalar(select(func.count(PriceObservation.id))) or 0
        last_market_timestamp = session.scalar(select(func.max(PriceObservation.market_timestamp)))
        last_retrieval_timestamp = session.scalar(select(func.max(PriceObservation.ingested_at)))
        latest_market_timestamp_by_exchange = {
            exchange: timestamp
            for exchange, timestamp in session.execute(
                select(SecurityRecord.exchange, func.max(PriceObservation.market_timestamp))
                .join(PriceObservation, PriceObservation.security_id == SecurityRecord.id)
                .group_by(SecurityRecord.exchange)
            )
        }
        price_quality_alerts = {
            flag: session.scalar(
                select(func.count(PriceObservation.id)).where(
                    PriceObservation.quality_flags_json.contains(flag)
                )
            )
            or 0
            for flag in (
                "zero_volume",
                "price_jump_over_20_percent",
                "calendar_gap_over_4_days",
            )
        }
        price_quality_alerts["unvalidated_observation"] = (
            session.scalar(
                select(func.count(PriceObservation.id)).where(
                    PriceObservation.validation_status != "valid"
                )
            )
            or 0
        )
        health = {
            row.source_name: row for row in session.scalars(select(SourceHealthRecord)).all()
        }

    diagnostics = []
    for source in sources(config):
        recorded = health.get(source.name)
        diagnostics.append(
            SourceDiagnostic(
                **source.model_dump(
                    exclude={"availability", "last_checked_at", "message"}
                ),
                availability=(
                    source.availability
                    if source.availability == "fixture" or recorded is None
                    else recorded.status
                ),
                last_checked_at=recorded.checked_at if recorded else source.last_checked_at,
                message=recorded.message if recorded else source.message,
                last_success_at=recorded.last_success_at if recorded else None,
                last_failure_at=recorded.last_failure_at if recorded else None,
                consecutive_failures=recorded.consecutive_failures if recorded else 0,
            )
        )

    issues = []
    if config.market_data_mode == "fixture":
        issues.append("Đang dùng fixture tổng hợp; mọi số giá chỉ phục vụ kiểm thử.")
    if not price_observations_count:
        issues.append("Chưa có quan sát giá nào được lưu trong cơ sở dữ liệu.")
    if missing_price_symbols:
        issues.append(
            f"{len(missing_price_symbols)} mã đang hoạt động chưa có lịch sử giá được lưu."
        )
    if missing_financial_symbols:
        issues.append(
            f"{len(missing_financial_symbols)} mã đang hoạt động chưa có BCTC được lưu."
        )
    if sync_error_records:
        issues.append(f"Có {sync_error_records} lỗi đồng bộ được lưu để xử lý.")
    if price_quality_alerts["price_jump_over_20_percent"]:
        issues.append(
            "Có biến động giá trên 20%; cần đối chiếu corporate action và nguồn gốc trước khi dùng."
        )
    if price_quality_alerts["calendar_gap_over_4_days"]:
        issues.append(
            "Có khoảng trống lịch trên 4 ngày; đây là cảnh báo sơ bộ vì chưa có lịch nghỉ HOSE/HNX/UPCoM chính thức."
        )
    if any(item.availability == "configured" and item.last_success_at is None for item in diagnostics):
        issues.append("Có nguồn đã cấu hình nhưng chưa có lần truy xuất thành công được xác minh.")
    if active_securities_count < 100:
        issues.append("Securities master mới là tập bootstrap, chưa có độ phủ toàn thị trường.")

    return DataQualityReport(
        generated_at=datetime.now(UTC),
        market_data_mode="fixture" if config.market_data_mode == "fixture" else "live",
        securities_count=securities_count,
        active_securities_count=active_securities_count,
        exchange_distribution=exchange_distribution,
        price_observations_count=price_observations_count,
        symbols_with_price_history=len(active_with_prices),
        symbols_missing_price_history=len(missing_price_symbols),
        symbols_with_financial_statements=len(active_with_financials),
        symbols_missing_financial_statements=len(missing_financial_symbols),
        price_coverage_percent=round(
            len(active_with_prices) / active_securities_count * 100, 2
        )
        if active_securities_count
        else 0,
        financial_coverage_percent=round(
            len(active_with_financials) / active_securities_count * 100, 2
        )
        if active_securities_count
        else 0,
        missing_price_symbols=missing_price_symbols[:50],
        missing_financial_symbols=missing_financial_symbols[:50],
        sync_error_records=sync_error_records,
        failed_sync_symbols=failed_sync_symbols[:50],
        price_quality_alerts=price_quality_alerts,
        latest_market_timestamp_by_exchange=latest_market_timestamp_by_exchange,
        last_market_timestamp=last_market_timestamp,
        last_retrieval_timestamp=last_retrieval_timestamp,
        sources=diagnostics,
        issues=issues,
    )


@app.get("/api/v1/market/overview", response_model=MarketOverview)
def market_overview() -> MarketOverview:
    return build_market_overview()


@app.post("/api/v1/market/reports/{report_type}", response_model=DailyMarketReport)
def market_report_create(
    report_type: str,
    trading_date: date | None = None,
    principal: Principal = Depends(require_admin),
) -> DailyMarketReport:
    try:
        return create_daily_market_report(report_type, trading_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/market/reports", response_model=list[DailyMarketReport])
def market_reports(limit: int = Query(50, ge=1, le=200)) -> list[DailyMarketReport]:
    return list_report_snapshots(limit)


@app.post("/api/v1/portfolios", response_model=dict)
def portfolio_create(
    payload: PortfolioCreate,
    request: Request,
    principal: Principal = Depends(require_admin),
):
    try:
        row = create_portfolio(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_success(request, principal, row, action="portfolios.create")
    return {"id": row.id, "name": row.name, "base_currency": row.base_currency}


@app.post("/api/v1/portfolios/{portfolio_id}/transactions", response_model=dict)
def portfolio_transaction_create(
    portfolio_id: int,
    payload: PortfolioTransactionInput,
    request: Request,
    principal: Principal = Depends(require_admin),
):
    try:
        row, inserted = add_transaction(portfolio_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_success(request, principal, row, action="portfolios.transactions.create")
    return {"id": row.id, "external_id": row.external_id, "inserted": inserted}


@app.post(
    "/api/v1/portfolios/{portfolio_id}/transactions/import",
    response_model=PortfolioImportResult,
)
def portfolio_transactions_import(
    portfolio_id: int,
    request: Request,
    csv_content: str = Body(media_type="text/csv"),
    source_name: str = Header(default="user-authorized-portfolio", alias="X-Source-Name"),
    principal: Principal = Depends(require_admin),
):
    if len(csv_content.encode("utf-8")) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV is too large.")
    result = import_transactions_csv(portfolio_id, csv_content, source_name[:128])
    if (
        result.rejected
        and not result.inserted
        and not result.skipped
        and any("Portfolio không tồn tại" in error for error in result.errors)
    ):
        raise HTTPException(status_code=404, detail="Portfolio không tồn tại")
    audit_success(request, principal, result, action="portfolios.transactions.import")
    return result


@app.get("/api/v1/portfolios/{portfolio_id}", response_model=PortfolioSummary)
def portfolio_get(
    portfolio_id: int, principal: Principal = Depends(require_admin)
) -> PortfolioSummary:
    try:
        return portfolio_summary(portfolio_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/social/analyze", response_model=SocialBatchResult)
def social_analyze(
    payload: SocialBatchRequest,
    request: Request,
    principal: Principal = Depends(require_admin),
) -> SocialBatchResult:
    """Analyze only user-authorized text; no social platform is scraped."""
    result = analyze_social_batch(payload)
    audit_success(request, principal, result, action="social.analyze")
    return result


@app.get("/api/v1/stocks/search", response_model=list[Security])
async def search(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(20, ge=1, le=100),
    include_inactive: bool = False,
):
    with SessionLocal() as session:
        return SecuritiesRepository(session).search(q, limit, include_inactive)


@app.get("/api/v1/securities", response_model=SecuritiesExplorerResponse)
def securities_explorer(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    q: str | None = Query(default=None, max_length=100),
    exchange: str | None = Query(default=None, pattern="^(HOSE|HNX|UPCOM)$"),
    sector: str | None = Query(default=None, max_length=128),
    listing_status: str | None = Query(
        default=None, pattern="^(active|inactive|delisted|suspended)$"
    ),
    sort_by: str = Query(default="symbol", pattern="^(symbol|name|price|change|volume)$"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> SecuritiesExplorerResponse:
    return list_securities(
        page=page,
        page_size=page_size,
        query=q,
        exchange=exchange,
        sector=sector,
        listing_status=listing_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@app.get("/api/v1/stocks/{symbol}", response_model=Security)
async def stock(symbol: str):
    with SessionLocal() as session:
        result = SecuritiesRepository(session).get(symbol)
    if result is None:
        raise HTTPException(
            404, detail={"code": "symbol_not_found", "message": "Mã chưa được hỗ trợ."}
        )
    return result


@app.post("/api/v1/securities/import", response_model=SecuritiesImportResult)
def import_securities(
    request: Request,
    csv_content: str = Body(media_type="text/csv"),
    source_name: str = Header(default="user-authorized-import", alias="X-Source-Name"),
    principal: Principal = Depends(require_admin),
):
    """Import an authorized CSV export; never downloads protected exchange data implicitly."""
    if len(csv_content.encode("utf-8")) > 1_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV is too large."
        )
    fieldnames = set(csv_content.splitlines()[0].split(",")) if csv_content.strip() else set()
    required_fields = {"symbol", "name", "exchange"}
    if not required_fields.issubset(fieldnames):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_csv_schema", "required": sorted(required_fields)},
        )
    result = import_securities_csv(csv_content, source_name[:128])
    record_file_import(
        capability=DataCapability.SECURITIES_METADATA,
        symbol=None,
        inserted=result.inserted,
        updated=result.updated,
        skipped=0,
        rejected=result.rejected,
        source_name=source_name[:128],
    )
    audit_success(request, principal, result)
    return result


@app.post("/api/v1/securities/import/xlsx", response_model=SecuritiesImportResult)
def import_securities_workbook(
    request: Request,
    workbook: bytes = Body(media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    source_name: str = Header(default="user-authorized-import", alias="X-Source-Name"),
    principal: Principal = Depends(require_admin),
):
    """Incrementally import an authorized XLSX securities registry."""
    if len(workbook) > 2_000_000:
        raise HTTPException(status_code=413, detail="XLSX is too large.")
    try:
        result = import_securities_xlsx(workbook, source_name[:128])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_file_import(
        capability=DataCapability.SECURITIES_METADATA,
        symbol=None,
        inserted=result.inserted,
        updated=result.updated,
        skipped=0,
        rejected=result.rejected,
        source_name=source_name[:128],
    )
    audit_success(request, principal, result, action="securities.import.xlsx")
    return result


@app.post(
    "/api/v1/stocks/{symbol}/corporate-actions/import",
    response_model=CorporateActionImportResult,
)
def corporate_actions_import(
    symbol: str,
    request: Request,
    csv_content: str = Body(media_type="text/csv"),
    source_name: str = Header(default="user-authorized-corporate-actions", alias="X-Source-Name"),
    principal: Principal = Depends(require_admin),
):
    if len(csv_content.encode("utf-8")) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV is too large.")
    try:
        result = import_corporate_actions(symbol, csv_content, source_name[:128])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_file_import(
        capability=DataCapability.CORPORATE_ACTIONS,
        symbol=symbol,
        inserted=result.inserted,
        updated=result.updated,
        skipped=0,
        rejected=result.rejected,
        source_name=source_name[:128],
    )
    audit_success(request, principal, result, action="corporate_actions.import")
    return result


@app.get("/api/v1/stocks/{symbol}/corporate-actions", response_model=list[CorporateAction])
def corporate_actions(symbol: str):
    try:
        return list_corporate_actions(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/fundamentals/calculate", response_model=FinancialMetricResult)
def fundamentals_calculate(inputs: FinancialInputs) -> FinancialMetricResult:
    return calculate_financial_metrics(inputs)


@app.post(
    "/api/v1/stocks/{symbol}/financials/import",
    response_model=FinancialStatementImportResult,
)
def import_financials(
    symbol: str,
    request: Request,
    csv_content: str = Body(media_type="text/csv"),
    source_name: str = Header(default="user-authorized-financial-export", alias="X-Source-Name"),
    principal: Principal = Depends(require_admin),
):
    if len(csv_content.encode("utf-8")) > 2_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV is too large."
        )
    try:
        with SessionLocal() as session:
            result = FinancialRepository(session).import_csv(symbol, csv_content, source_name[:128])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    record_file_import(
        capability=DataCapability.INCOME_STATEMENT,
        symbol=symbol,
        inserted=result.inserted_periods + result.inserted_items,
        updated=result.updated_periods + result.updated_items,
        skipped=result.skipped_items,
        rejected=result.rejected,
        source_name=source_name[:128],
    )
    audit_success(request, principal, result, action="financials.import")
    return result


@app.get(
    "/api/v1/stocks/{symbol}/financial-statements",
    response_model=FinancialStatementsResponse,
)
def financial_statements(
    symbol: str,
    period_type: str | None = Query(default=None, pattern="^(quarter|year|ttm)$"),
    statement_scope: str | None = Query(
        default=None, pattern="^(consolidated|separate)$"
    ),
    limit: int = Query(12, ge=1, le=40),
) -> FinancialStatementsResponse:
    try:
        with SessionLocal() as session:
            return FinancialRepository(session).statements(
                symbol,
                period_type=period_type,
                statement_scope=statement_scope,
                limit=limit,
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/v1/stocks/{symbol}/financials/validation-reports",
    response_model=list[FinancialValidationReport],
)
def financial_validation_reports(
    symbol: str,
    limit: int = Query(50, ge=1, le=200),
) -> list[FinancialValidationReport]:
    try:
        with SessionLocal() as session:
            return FinancialRepository(session).validation_reports(symbol, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/sync/prices/{symbol}", response_model=DataSyncRun)
async def sync_prices(
    symbol: str,
    request: Request,
    provider: str = Query(default="auto", pattern="^(auto|yahoo|fixture)$"),
    mode: str = Query(default="auto", pattern="^(auto|initial|incremental)$"),
    limit: int = Query(520, ge=30, le=520),
    principal: Principal = Depends(require_admin),
    config: Settings = Depends(get_settings),
) -> DataSyncRun:
    try:
        result = await DataSyncService(config).sync_prices(
            symbol, provider_id=provider, requested_mode=mode, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audit_success(request, principal, result, action="data_sync.prices")
    return result


@app.post("/api/v1/sync/financials/{symbol}", response_model=DataSyncRun)
def sync_financial_statements(
    symbol: str,
    request: Request,
    principal: Principal = Depends(require_admin),
    config: Settings = Depends(get_settings),
) -> DataSyncRun:
    try:
        result = DataSyncService(config).sync_financials(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_success(request, principal, result, action="data_sync.financials")
    return result


@app.get("/api/v1/sync/runs", response_model=list[DataSyncRun])
def sync_runs(
    symbol: str | None = None,
    provider: str | None = None,
    capability: str | None = None,
    run_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(RUNNING|SUCCESS|PARTIAL|FAILED|BLOCKED)$",
    ),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_admin),
) -> list[DataSyncRun]:
    return list_sync_runs(
        symbol=symbol,
        provider=provider,
        capability=capability,
        status=run_status,
        limit=limit,
    )


@app.get("/api/v1/stocks/{symbol}/fundamentals", response_model=FinancialMetricResult)
def fundamentals(symbol: str) -> FinancialMetricResult:
    try:
        with SessionLocal() as session:
            return FinancialRepository(session).calculate_latest(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/api/v1/stocks/{symbol}/fundamentals/history", response_model=FinancialTrendResponse)
def fundamentals_history(
    symbol: str,
    period_type: str = Query("year", pattern="^(quarter|year|ttm)$"),
    statement_scope: str = Query("consolidated", pattern="^(consolidated|separate)$"),
    limit: int = Query(8, ge=1, le=20),
) -> FinancialTrendResponse:
    try:
        with SessionLocal() as session:
            return FinancialRepository(session).history(
                symbol,
                period_type=period_type,
                statement_scope=statement_scope,
                limit=limit,
            )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _calculate_valuation(inputs: ValuationRequest) -> ValuationResult:
    result = calculate_relative_valuation(inputs)
    return result


@app.post("/api/v1/fundamentals/valuation", response_model=ValuationResult)
def valuation(inputs: ValuationRequest) -> ValuationResult:
    """Public calculation only; it never writes shared state."""
    return _calculate_valuation(inputs)


@app.post("/api/v1/fundamentals/valuation/dcf", response_model=ValuationResult)
def dcf_valuation(inputs: DCFRequest) -> ValuationResult:
    """Public deterministic DCF calculation; assumptions are explicit and never persisted."""
    return calculate_dcf_valuation(inputs)


@app.post(
    "/api/v1/fundamentals/valuation/dcf/sensitivity",
    response_model=DCFSensitivityResult,
)
def dcf_sensitivity(inputs: DCFSensitivityRequest) -> DCFSensitivityResult:
    """Return null for invalid rate pairs instead of inventing a valuation."""
    return calculate_dcf_sensitivity(inputs)


@app.post("/api/v1/fundamentals/valuation/persist", response_model=ValuationResult)
def valuation_persist(
    inputs: ValuationRequest,
    request: Request,
    principal: Principal = Depends(require_admin),
) -> ValuationResult:
    result = _calculate_valuation(inputs)
    with SessionLocal() as session:
        security = session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == inputs.symbol.strip().upper())
        )
        if security is not None:
            for scenario, value in result.scenarios.items():
                session.add(
                    ValuationResultRecord(
                        security_id=security.id,
                        method=result.method,
                        scenario=scenario,
                        value=value,
                        assumptions_json=json.dumps(result.assumptions, ensure_ascii=False),
                        source_name=inputs.assumption_source,
                        created_at=result.calculated_at,
                    )
                )
            session.commit()
    audit_success(request, principal, result, action="valuation.persist")
    return result


async def translate_connector_error(operation):
    try:
        return await operation
    except ConnectorError as exc:
        raise HTTPException(
            503, detail={"code": "source_unavailable", "message": str(exc)}
        ) from exc


@app.get("/api/v1/stocks/{symbol}/prices", response_model=PriceSeries)
async def prices(
    symbol: str, limit: int = Query(260, ge=30, le=520), svc: AnalysisService = Depends(service)
):
    return await translate_connector_error(svc.prices(symbol, limit))


@app.get("/api/v1/stocks/{symbol}/technicals", response_model=TechnicalSnapshot)
async def technicals(symbol: str, svc: AnalysisService = Depends(service)):
    return (await translate_connector_error(svc.analyze(symbol))).technicals


@app.get("/api/v1/stocks/{symbol}/news")
async def news(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, max_length=128),
    event_category: str | None = Query(None, max_length=32),
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    svc: AnalysisService = Depends(service),
):
    if published_from and published_to and published_from > published_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="published_from must be before published_to",
        )
    with SessionLocal() as session:
        cached = NewsRepository(session).list(
            symbol,
            limit,
            source=source,
            event_category=event_category,
            published_from=published_from,
            published_to=published_to,
        )
    if cached:
        return {"items": cached, "coverage_note": "Metadata RSS đã chuẩn hóa/lưu trữ; có thể không đầy đủ."}
    with SessionLocal() as session:
        security = SecuritiesRepository(session).get(symbol)
    if security is None:
        raise HTTPException(404, detail={"code": "symbol_not_found", "message": "Mã chưa được hỗ trợ."})
    await svc.related_news(security, limit=100)
    with SessionLocal() as session:
        filtered = NewsRepository(session).list(
            symbol,
            limit,
            source=source,
            event_category=event_category,
            published_from=published_from,
            published_to=published_to,
        )
    return {
        "items": filtered,
        "coverage_note": "Metadata RSS đã chuẩn hóa/lưu trữ; có thể không đầy đủ.",
    }


@app.post("/api/v1/analyst/chat", response_model=AnalystResponse)
async def analyst_chat(
    payload: AnalystRequest, request: Request, svc: AnalysisService = Depends(service)
):
    enforce_llm_rate_limit(request, settings)
    audit_event(
        request,
        action="analyst.chat",
        metadata={"symbol": payload.symbol.strip().upper(), "question_length": len(payload.question)},
    )
    return await AnalystService(settings, svc).answer(payload)


@app.post("/api/v1/jobs/eod/{symbol}", response_model=JobResult)
async def enqueue_eod(symbol: str, payload: JobRequest | None = None, request: Request = None, principal: Principal = Depends(require_admin)):
    try:
        job = AutomationService(
            AnalysisService(settings),
            settings.automation_max_retries,
            settings.automation_lease_seconds,
            settings.market_timezone,
        ).enqueue_eod(symbol, payload.scheduled_for if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request is not None: audit_success(request, principal, {"job_id": job.id}, action="jobs.enqueue")
    return job_schema(job)


@app.get("/api/v1/jobs", response_model=list[JobResult])
def list_jobs(principal: Principal = Depends(require_admin)):
    with SessionLocal() as session:
        return [job_schema(job) for job in session.query(JobRecord).order_by(JobRecord.id.desc()).limit(100).all()]


@app.post("/api/v1/jobs/{job_id}/run", response_model=JobResult)
async def run_job(job_id: int, principal: Principal = Depends(require_admin)):
    job = await AutomationService(
        AnalysisService(settings),
        settings.automation_max_retries,
        settings.automation_lease_seconds,
        settings.market_timezone,
    ).run(job_id)
    return job_schema(job)


@app.post("/api/v1/watchlists", response_model=dict)
def watchlist_create(payload: WatchlistRequest, principal: Principal = Depends(require_admin)):
    row = create_watchlist(payload.name)
    return {"id": row.id, "name": row.name, "owner": row.owner}


@app.post("/api/v1/watchlists/{watchlist_id}/items", response_model=dict)
def watchlist_add(watchlist_id: int, payload: WatchlistItemRequest, principal: Principal = Depends(require_admin)):
    try: row = add_watchlist_item(watchlist_id, payload.symbol)
    except LookupError as exc: raise HTTPException(404, detail=str(exc)) from exc
    return {"id": row.id, "watchlist_id": row.watchlist_id, "symbol": row.symbol}


@app.post("/api/v1/watchlists/{watchlist_id}/rules", response_model=dict)
def watchlist_rule(watchlist_id: int, payload: AlertRuleRequest, principal: Principal = Depends(require_admin)):
    try: row = create_alert_rule(watchlist_id, payload.rule_type, payload.threshold)
    except LookupError as exc: raise HTTPException(404, detail=str(exc)) from exc
    return {"id": row.id, "watchlist_id": row.watchlist_id, "rule_type": row.rule_type, "threshold": row.threshold, "enabled": row.enabled}


@app.get("/api/v1/stocks/{symbol}/analysis", response_model=AnalysisResponse)
async def analysis(symbol: str, svc: AnalysisService = Depends(service)):
    return await translate_connector_error(svc.analyze(symbol))


@app.post("/api/v1/stocks/{symbol}/reports")
async def report(symbol: str, svc: AnalysisService = Depends(service)):
    result = await translate_connector_error(svc.analyze(symbol))
    return StreamingResponse(
        BytesIO(build_pdf(result)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{result.security.symbol}-research-report.pdf"'
        },
    )
