import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analyst import AnalystService
from app.analytics.fundamental import calculate_financial_metrics
from app.analytics.valuation import calculate_dcf_valuation, calculate_relative_valuation
from app.auth import Principal, audit_event, audit_success, enforce_llm_rate_limit, require_admin
from app.automation import (
    AutomationService,
    add_watchlist_item,
    create_alert_rule,
    create_watchlist,
    job_schema,
)
from app.config import Settings, get_settings
from app.connectors.base import ConnectorError
from app.connectors.fireant import FireAntConnector
from app.database import (
    JobRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
    SourceHealthRecord,
    ValuationResultRecord,
    init_db,
)
from app.registry import import_securities_csv, seed_registry_if_empty
from app.reporting import build_pdf
from app.repositories import FinancialRepository, NewsRepository, SecuritiesRepository
from app.schemas import (
    AlertRuleRequest,
    AnalysisResponse,
    AnalystRequest,
    AnalystResponse,
    DataQualityReport,
    DCFRequest,
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementImportResult,
    FinancialTrendResponse,
    JobRequest,
    JobResult,
    PriceSeries,
    SecuritiesImportResult,
    Security,
    SourceDiagnostic,
    SourceStatus,
    TechnicalSnapshot,
    ValuationRequest,
    ValuationResult,
    WatchlistItemRequest,
    WatchlistRequest,
)
from app.services import AnalysisService


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


@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_request_bytes:
        return StreamingResponse(
            iter([b'{"detail":"Request body is too large."}']),
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            media_type="application/json",
        )
    return await call_next(request)
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
        securities_count = session.scalar(select(func.count(SecurityRecord.id))) or 0
        active_securities_count = (
            session.scalar(
                select(func.count(SecurityRecord.id)).where(
                    SecurityRecord.listing_status == "active"
                )
            )
            or 0
        )
        price_observations_count = session.scalar(select(func.count(PriceObservation.id))) or 0
        last_market_timestamp = session.scalar(select(func.max(PriceObservation.market_timestamp)))
        last_retrieval_timestamp = session.scalar(select(func.max(PriceObservation.ingested_at)))
        health = {
            row.source_name: row for row in session.scalars(select(SourceHealthRecord)).all()
        }

    diagnostics = []
    for source in sources(config):
        recorded = health.get(source.name)
        diagnostics.append(
            SourceDiagnostic(
                **source.model_dump(exclude={"last_checked_at", "message"}),
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
    if any(item.availability == "configured" and item.last_success_at is None for item in diagnostics):
        issues.append("Có nguồn đã cấu hình nhưng chưa có lần truy xuất thành công được xác minh.")
    if active_securities_count < 100:
        issues.append("Securities master mới là tập bootstrap, chưa có độ phủ toàn thị trường.")

    return DataQualityReport(
        generated_at=datetime.now(UTC),
        market_data_mode="fixture" if config.market_data_mode == "fixture" else "live",
        securities_count=securities_count,
        active_securities_count=active_securities_count,
        price_observations_count=price_observations_count,
        last_market_timestamp=last_market_timestamp,
        last_retrieval_timestamp=last_retrieval_timestamp,
        sources=diagnostics,
        issues=issues,
    )


@app.get("/api/v1/stocks/search", response_model=list[Security])
async def search(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(20, ge=1, le=100),
    include_inactive: bool = False,
):
    with SessionLocal() as session:
        return SecuritiesRepository(session).search(q, limit, include_inactive)


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
    audit_success(request, principal, result)
    return result


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
    audit_success(request, principal, result, action="financials.import")
    return result


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
    job = AutomationService(AnalysisService(settings), settings.automation_max_retries).enqueue_eod(symbol, payload.scheduled_for if payload else None)
    if request is not None: audit_success(request, principal, {"job_id": job.id}, action="jobs.enqueue")
    return job_schema(job)


@app.get("/api/v1/jobs", response_model=list[JobResult])
def list_jobs(principal: Principal = Depends(require_admin)):
    with SessionLocal() as session:
        return [job_schema(job) for job in session.query(JobRecord).order_by(JobRecord.id.desc()).limit(100).all()]


@app.post("/api/v1/jobs/{job_id}/run", response_model=JobResult)
async def run_job(job_id: int, principal: Principal = Depends(require_admin)):
    job = await AutomationService(AnalysisService(settings), settings.automation_max_retries).run(job_id)
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
