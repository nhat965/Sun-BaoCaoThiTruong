import os

os.environ["MARKET_DATA_MODE"] = "fixture"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app.main import app


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
