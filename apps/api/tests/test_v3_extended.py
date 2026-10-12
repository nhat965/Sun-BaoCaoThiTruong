from datetime import UTC, datetime

from app.connectors.news import classify_event, group_hash, relevance
from app.schemas import Security


def test_news_pipeline_classifies_and_deduplicates_group():
    security = Security(symbol="HPG", name="Tập đoàn Hòa Phát", exchange="HOSE", aliases=["Hoa Phat"])
    assert classify_event("HPG công bố lợi nhuận quý mới") == "earnings"
    assert relevance("HPG tăng trưởng lợi nhuận", security) >= 0.7
    stamp = datetime(2025, 1, 2, tzinfo=UTC)
    assert group_hash("HPG lợi nhuận", stamp) == group_hash("HPG lợi nhuận", stamp)
    assert group_hash("HPG lợi nhuận", stamp) != group_hash("HPG lợi nhuận", datetime(2025, 1, 3, tzinfo=UTC))
