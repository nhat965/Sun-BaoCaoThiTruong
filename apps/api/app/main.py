from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.analytics.fundamental import calculate_financial_metrics
from app.config import Settings, get_settings
from app.connectors.base import ConnectorError
from app.connectors.fireant import FireAntConnector
from app.database import SessionLocal, init_db
from app.registry import import_securities_csv, seed_registry_if_empty
from app.reporting import build_pdf
from app.repositories import SecuritiesRepository
from app.schemas import (
    AnalysisResponse,
    FinancialInputs,
    FinancialMetricResult,
    PriceSeries,
    SecuritiesImportResult,
    Security,
    SourceStatus,
    TechnicalSnapshot,
)
from app.services import AnalysisService


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_registry_if_empty()
    yield


app = FastAPI(title="Mạch Thị Trường API", version="0.2.0", lifespan=lifespan)
settings = get_settings()
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
        SourceStatus(
            name="VnExpress RSS",
            capabilities=["news_metadata"],
            authentication="none",
            availability="configured",
            freshness="RSS publication schedule",
            licensing="Metadata and links only.",
        ),
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
    csv_content: str = Body(media_type="text/csv"),
    source_name: str = Header(default="user-authorized-import", alias="X-Source-Name"),
):
    """Import an authorized CSV export; never downloads protected exchange data implicitly."""
    return import_securities_csv(csv_content, source_name)


@app.post("/api/v1/fundamentals/calculate", response_model=FinancialMetricResult)
def fundamentals_calculate(inputs: FinancialInputs) -> FinancialMetricResult:
    return calculate_financial_metrics(inputs)


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
    analysis = await translate_connector_error(svc.analyze(symbol))
    return {"items": analysis.news, "coverage_note": "Khớp từ khóa trên RSS; có thể không đầy đủ."}


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
