from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import admin_rate_limiter
from app.config import Settings, get_settings
from app.database import (
    FinancialMetricRecord,
    FinancialPeriodRecord,
    FinancialStatementItemRecord,
    FinancialValidationReportRecord,
    SessionLocal,
)
from app.main import app


def test_hpg_and_fpt_authorized_statement_flow_is_idempotent():
    token = "task02-acceptance-token-long-enough"
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_mode="fixture",
        admin_api_token=token,
        admin_rate_limit_per_minute=1000,
    )
    csv = (
        "period_end,period_type,fiscal_year,statement_type,item_code,value,unit,"
        "verification_status,statement_scope,source_url\n"
        "2099-12-31T00:00:00+00:00,year,2099,income,revenue,100,MILLION_VND,"
        "verified,consolidated,https://authorized.example/acceptance.csv\n"
        "2099-12-31T00:00:00+00:00,year,2099,income,net_income,10,MILLION_VND,"
        "verified,consolidated,https://authorized.example/acceptance.csv\n"
    )
    headers = {"Authorization": f"Bearer {token}", "X-Source-Name": "acceptance-file"}
    try:
        with TestClient(app) as client:
            for symbol in ("HPG", "FPT"):
                assert client.get("/api/v1/stocks/search", params={"q": symbol}).status_code == 200
                first = client.post(f"/api/v1/stocks/{symbol}/financials/import", headers=headers, content=csv)
                assert first.status_code == 200
                replay = client.post(f"/api/v1/stocks/{symbol}/financials/import", headers=headers, content=csv)
                assert replay.status_code == 200
                assert replay.json()["inserted_items"] == 0
                assert replay.json()["skipped_items"] >= 2
                fundamentals = client.get(f"/api/v1/stocks/{symbol}/fundamentals")
                assert fundamentals.status_code == 200
                payload = fundamentals.json()
                assert payload["metrics"]["revenue_growth_percent"] is None
                assert payload["metric_metadata"]["revenue_growth_percent"]["input_status"] == "incomplete"
                assert payload["period_end"].startswith("2099-12-31")
    finally:
        app.dependency_overrides.clear()
        admin_rate_limiter.reset()
        # This test intentionally uses a future-dated fixture.  Never leave it
        # in the developer/acceptance database after pytest exits.
        with SessionLocal() as session:
            period_ids = list(
                session.scalars(
                    select(FinancialPeriodRecord.id).where(
                        FinancialPeriodRecord.source_name == "acceptance-file",
                        FinancialPeriodRecord.fiscal_year == 2099,
                    )
                ).all()
            )
            if period_ids:
                session.execute(
                    delete(FinancialMetricRecord).where(
                        FinancialMetricRecord.period_id.in_(period_ids)
                    )
                )
                session.execute(
                    delete(FinancialStatementItemRecord).where(
                        FinancialStatementItemRecord.period_id.in_(period_ids)
                    )
                )
                session.execute(
                    delete(FinancialValidationReportRecord).where(
                        FinancialValidationReportRecord.period_id.in_(period_ids)
                    )
                )
                session.execute(
                    delete(FinancialPeriodRecord).where(
                        FinancialPeriodRecord.id.in_(period_ids)
                    )
                )
                session.commit()
