import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_DATA_MODE"] = "fixture"

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.config import Settings, get_settings
from app.database import PriceObservation, SecurityRecord, SessionLocal
from app.main import app

ADMIN_TOKEN = "task02-admin-token-long-enough"


def _settings() -> Settings:
    return Settings(
        market_data_mode="fixture",
        admin_api_token=ADMIN_TOKEN,
        admin_rate_limit_per_minute=1000,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_provider_catalog_separates_documented_and_enabled_capabilities():
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/providers")
            assert response.status_code == 200
            providers = {item["provider_id"]: item for item in response.json()}
            assert providers["fixture"]["enabled_capabilities"] == ["historical_ohlcv"]
            assert providers["fireant"]["enabled_capabilities"] == []
            assert providers["fireant"]["availability"] == "blocked"
            assert "balance_sheet" in providers["fiingroup"]["documented_capabilities"]
            assert providers["ssi_fastconnect"]["enabled_capabilities"] == []
    finally:
        app.dependency_overrides.clear()


def test_price_sync_is_incremental_and_does_not_duplicate_observations():
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            with SessionLocal() as session:
                security_id = session.scalar(
                    select(SecurityRecord.id).where(SecurityRecord.symbol == "HPG")
                )
                session.execute(
                    delete(PriceObservation).where(
                        PriceObservation.security_id == security_id,
                        PriceObservation.provider == "Synthetic fixture (development only)",
                    )
                )
                session.commit()

            first = client.post(
                "/api/v1/sync/prices/HPG",
                params={"provider": "fixture", "limit": 60},
                headers=_headers(),
            )
            assert first.status_code == 200
            assert first.json()["sync_mode"] == "initial"
            assert first.json()["inserted_count"] == 60

            with SessionLocal() as session:
                before = session.scalar(
                    select(func.count(PriceObservation.id)).where(
                        PriceObservation.security_id == security_id,
                        PriceObservation.provider == "Synthetic fixture (development only)",
                    )
                )

            second = client.post(
                "/api/v1/sync/prices/HPG",
                params={"provider": "fixture", "limit": 60},
                headers=_headers(),
            )
            assert second.status_code == 200
            assert second.json()["sync_mode"] == "incremental"
            assert second.json()["inserted_count"] == 0

            with SessionLocal() as session:
                after = session.scalar(
                    select(func.count(PriceObservation.id)).where(
                        PriceObservation.security_id == security_id,
                        PriceObservation.provider == "Synthetic fixture (development only)",
                    )
                )
            assert before == after == 60
    finally:
        app.dependency_overrides.clear()


def test_financial_import_normalizes_units_and_protects_verified_values():
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            client.post(
                "/api/v1/securities/import",
                headers=_headers() | {"X-Source-Name": "authorized-registry"},
                content="symbol,name,exchange\nT02,Task 02 Test,HOSE\n",
            )
            base = (
                "period_end,period_type,fiscal_year,statement_type,item_code,value,unit,"
                "verification_status,statement_scope,source_url\n"
            )
            first = client.post(
                "/api/v1/stocks/T02/financials/import",
                headers=_headers() | {"X-Source-Name": "authorized-bctc"},
                content=base
                + "2025-12-31T00:00:00+00:00,year,2025,income,revenue,100,MILLION_VND,verified,consolidated,https://example.com/report\n",
            )
            assert first.status_code == 200
            assert first.json()["inserted_items"] == 1

            downgrade = client.post(
                "/api/v1/stocks/T02/financials/import",
                headers=_headers() | {"X-Source-Name": "unverified-copy"},
                content=base
                + "2025-12-31T00:00:00+00:00,year,2025,income,revenue,999,MILLION_VND,unverified,consolidated,https://example.com/unverified\n",
            )
            assert downgrade.status_code == 200
            assert downgrade.json()["skipped_items"] == 1

            stored = client.get("/api/v1/stocks/T02/financial-statements")
            assert stored.status_code == 200
            item = stored.json()["periods"][0]["items"][0]
            assert item["value"] == 100_000_000
            assert item["unit"] == "VND"
            assert item["raw_value"] == 100
            assert item["raw_unit"] == "MILLION_VND"
            assert item["verification_status"] == "verified"
    finally:
        app.dependency_overrides.clear()


def test_automatic_financial_sync_records_blocked_state_and_quality_error():
    app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(app) as client:
            blocked = client.post(
                "/api/v1/sync/financials/HPG", headers=_headers()
            )
            assert blocked.status_code == 200
            assert blocked.json()["status"] == "BLOCKED"
            assert "BLOCKED" in blocked.json()["error_message"]

            quality = client.get("/api/v1/data-quality").json()
            assert quality["sync_error_records"] >= 1
            assert "HPG" in quality["failed_sync_symbols"]
            assert "symbols_with_financial_statements" in quality
    finally:
        app.dependency_overrides.clear()


def test_licensed_https_financial_sync_imports_and_is_idempotent(monkeypatch):
    import httpx

    csv_data = (
        "period_end,period_type,fiscal_year,statement_type,item_code,value,unit,"
        "verification_status,statement_scope,source_url\n"
        "2025-12-31T00:00:00+00:00,year,2025,income,revenue,123,MILLION_VND,"
        "verified,consolidated,https://licensed.example/report\n"
    )
    calls = []

    def fake_get(self, url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200, content=csv_data.encode(), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_mode="fixture", admin_api_token=ADMIN_TOKEN,
        admin_rate_limit_per_minute=1000,
        financial_csv_url_template="https://licensed.example/{symbol}.csv",
        financial_csv_bearer_token="test-only-token",
        financial_csv_rights_confirmed=True,
    )
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/sync/financials/HPG", headers=_headers())
            assert first.status_code == 200
            assert first.json()["status"] == "SUCCESS"
            assert first.json()["inserted_count"] == 1
            second = client.post("/api/v1/sync/financials/HPG", headers=_headers())
            assert second.status_code == 200
            assert second.json()["inserted_count"] == 0
            assert second.json()["updated_count"] == 1
            assert all(url == "https://licensed.example/HPG.csv" for url, _ in calls)
            assert calls[0][1]["headers"]["Authorization"] == "Bearer test-only-token"
            stored = client.get("/api/v1/stocks/HPG/financial-statements")
            assert stored.status_code == 200
            assert any(
                item["item_code"] == "revenue" and item["value"] == 123000000
                for period in stored.json()["periods"]
                for item in period["items"]
            )
    finally:
        app.dependency_overrides.clear()


def test_financial_sync_requires_rights_and_safe_url(monkeypatch):
    import httpx

    def unexpected_request(self, url, **kwargs):
        raise AssertionError("Source must not be contacted without permission")

    monkeypatch.setattr(httpx.Client, "get", unexpected_request)
    for url, confirmed in (
        ("https://licensed.example/{symbol}.csv", False),
        ("http://licensed.example/{symbol}.csv", True),
        ("https://user:secret@licensed.example/{symbol}.csv", True),
    ):
        app.dependency_overrides[get_settings] = lambda url=url, confirmed=confirmed: Settings(
            market_data_mode="fixture", admin_api_token=ADMIN_TOKEN,
            admin_rate_limit_per_minute=1000,
            financial_csv_url_template=url,
            financial_csv_rights_confirmed=confirmed,
        )
        try:
            with TestClient(app) as client:
                result = client.post("/api/v1/sync/financials/HPG", headers=_headers())
                assert result.status_code == 200
                assert result.json()["status"] == "BLOCKED"
        finally:
            app.dependency_overrides.clear()
