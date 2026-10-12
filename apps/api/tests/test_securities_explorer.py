import os

os.environ["MARKET_DATA_MODE"] = "fixture"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app.main import app


def test_explorer_lists_real_registry_with_server_pagination_and_missing_values():
    with TestClient(app) as client:
        client.get("/api/v1/stocks/HPG/analysis")
        response = client.get("/api/v1/securities", params={"page_size": 5})
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 13
        assert payload["page"] == 1
        assert payload["page_size"] == 5
        assert payload["total_pages"] == (payload["total"] + 4) // 5
        assert len(payload["items"]) == 5
        assert payload["available_exchanges"] == ["HNX", "HOSE", "UPCOM"]

        final_page = client.get(
            "/api/v1/securities",
            params={"page": payload["total_pages"], "page_size": 5},
        ).json()
        assert 1 <= len(final_page["items"]) <= 5
        vnm = client.get("/api/v1/securities", params={"q": "VNM"}).json()["items"][0]
        assert vnm["latest_price"] is None
        assert vnm["change_percent"] is None
        assert vnm["volume"] is None
        assert vnm["pe"] is None
        assert vnm["pb"] is None


def test_explorer_search_filters_and_database_sorting():
    with TestClient(app) as client:
        client.get("/api/v1/stocks/HPG/analysis")
        hoa_phat = client.get("/api/v1/securities", params={"q": "Hoa Phat"}).json()
        assert hoa_phat["total"] == 1
        assert hoa_phat["items"][0]["symbol"] == "HPG"

        hose = client.get("/api/v1/securities", params={"exchange": "HOSE"}).json()
        assert hose["total"] == 7
        assert all(item["exchange"] == "HOSE" for item in hose["items"])

        materials = client.get(
            "/api/v1/securities", params={"sector": "Nguyên vật liệu"}
        ).json()
        assert {item["symbol"] for item in materials["items"]} == {"HPG", "HSG", "NKG"}

        by_volume = client.get(
            "/api/v1/securities",
            params={"sort_by": "volume", "sort_order": "desc"},
        ).json()
        assert by_volume["items"][0]["symbol"] == "HPG"
        assert by_volume["items"][0]["latest_price"] is not None


def test_explorer_rejects_unknown_filter_and_sort_values():
    with TestClient(app) as client:
        assert client.get("/api/v1/securities", params={"exchange": "NYSE"}).status_code == 422
        assert client.get("/api/v1/securities", params={"sort_by": "invented"}).status_code == 422
