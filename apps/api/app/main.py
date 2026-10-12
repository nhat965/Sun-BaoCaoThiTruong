import json
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analyst import AnalystService
from app.analytics.fundamental import calculate_financial_metrics
from app.analytics.valuation import calculate_relative_valuation
from app.auth import Principal, audit_success, require_admin
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
from app.database import JobRecord, SecurityRecord, SessionLocal, ValuationResultRecord, init_db
from app.registry import import_securities_csv, seed_registry_if_empty
from app.reporting import build_pdf
from app.repositories import FinancialRepository, NewsRepository, SecuritiesRepository
from app.schemas import (
    AlertRuleRequest,
    AnalysisResponse,
    AnalystRequest,
    AnalystResponse,
    FinancialInputs,
    FinancialMetricResult,
    FinancialStatementImportResult,
    JobRequest,
    JobResult,
    PriceSeries,
    SecuritiesImportResult,
    Security,
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
    return [
        SourceStatus(
            name="Yahoo Finance chart",
            capabilities=["search", "historical_prices"],
            authentication="none",
            availability="fixture" if config.market_data_mode == "fixture" else "configured",
            freshness="daily/delayed",
            licensing="Development connector; verify commercial redistribution rights.",
        ),
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


@app.post("/api/v1/fundamentals/valuation", response_model=ValuationResult)
def valuation(inputs: ValuationRequest) -> ValuationResult:
    result = calculate_relative_valuation(inputs)
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
async def news(symbol: str, svc: AnalysisService = Depends(service)):
    with SessionLocal() as session:
        cached = NewsRepository(session).list(symbol)
    if cached:
        return {"items": cached, "coverage_note": "Metadata RSS đã chuẩn hóa/lưu trữ; có thể không đầy đủ."}
    with SessionLocal() as session:
        security = SecuritiesRepository(session).get(symbol)
    if security is None:
        raise HTTPException(404, detail={"code": "symbol_not_found", "message": "Mã chưa được hỗ trợ."})
    return {"items": await svc.related_news(security), "coverage_note": "Metadata RSS; không tải toàn văn bài viết."}


@app.post("/api/v1/analyst/chat", response_model=AnalystResponse)
async def analyst_chat(payload: AnalystRequest, svc: AnalysisService = Depends(service)):
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
