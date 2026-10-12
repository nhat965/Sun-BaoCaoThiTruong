import os
from datetime import UTC, datetime

os.environ["MARKET_DATA_MODE"] = "fixture"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.repositories import NewsRepository
from app.schemas import NewsItem


def test_health_and_hpg_flow():
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        search = client.get("/api/v1/stocks/search", params={"q": "HPG"})
        assert search.status_code == 200 and search.json()[0]["symbol"] == "HPG"
        analysis = client.get("/api/v1/stocks/HPG/analysis")
        assert analysis.status_code == 200
        payload = analysis.json()
        assert payload["prices"]["provenance"]["mode"] == "fixture"
        assert payload["technicals"]["indicators"]["rsi14"]["value"] is not None
        assert payload["technicals"]["formula_version"] == "technical-v2"
        assert set(payload["technicals"]["component_scores"]) == {
            "trend",
            "momentum",
            "volume_confirmation",
            "volatility_risk",
        }
        assert payload["fundamental_status"] == "unavailable"

        quality = client.get("/api/v1/data-quality")
        assert quality.status_code == 200
        quality_payload = quality.json()
        assert quality_payload["market_data_mode"] == "fixture"
        assert quality_payload["price_observations_count"] >= 30
        fixture = next(
            source
            for source in quality_payload["sources"]
            if source["availability"] == "fixture"
        )
        assert fixture["last_success_at"] is not None
        assert quality_payload["issues"]


def test_pdf_report_and_validation():
    with TestClient(app) as client:
        report = client.post("/api/v1/stocks/HPG/reports")
        assert report.status_code == 200
        assert report.headers["content-type"] == "application/pdf"
        assert report.content.startswith(b"%PDF")
        assert client.get("/api/v1/stocks/search", params={"q": ""}).status_code == 422


def test_registry_search_without_diacritics_and_fundamental_calculator():
    with TestClient(app) as client:
        search = client.get("/api/v1/stocks/search", params={"q": "hoa phat"})
        assert search.status_code == 200
        assert search.json()[0]["symbol"] == "HPG"
        result = client.post(
            "/api/v1/fundamentals/calculate",
            json={"net_income": 10, "total_equity": 50},
        )
        assert result.status_code == 200
        assert result.json()["metrics"]["roe_percent"] == 20


def test_fireant_status_is_honestly_blocked_without_token():
    with TestClient(app) as client:
        result = client.get("/api/v1/sources/status")
        fireant = next(item for item in result.json() if item["name"] == "FireAnt")
        assert fireant["availability"] == "unavailable"
        assert fireant["message"].startswith("BLOCKED")


def test_news_filters_use_persisted_metadata():
    with TestClient(app) as client:
        with SessionLocal() as session:
            NewsRepository(session).store(
                "HPG",
                [
                    NewsItem(
                        title="HPG công bố lợi nhuận năm",
                        publisher="Authorized Feed A",
                        published_at=datetime(2026, 1, 10, tzinfo=UTC),
                        url="https://example.com/hpg-earnings",
                        related_symbols=["HPG"],
                        relevance_score=0.9,
                        event_category="earnings",
                    ),
                    NewsItem(
                        title="HPG triển khai dự án mới",
                        publisher="Authorized Feed B",
                        published_at=datetime(2026, 2, 10, tzinfo=UTC),
                        url="https://example.com/hpg-project",
                        related_symbols=["HPG"],
                        relevance_score=0.8,
                        event_category="investment",
                    ),
                ],
            )
        response = client.get(
            "/api/v1/stocks/HPG/news",
            params={"source": "Authorized Feed A", "event_category": "earnings"},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["publisher"] == "Authorized Feed A"
        invalid_range = client.get(
            "/api/v1/stocks/HPG/news",
            params={"published_from": "2026-03-01T00:00:00Z", "published_to": "2026-01-01T00:00:00Z"},
        )
        assert invalid_range.status_code == 422
