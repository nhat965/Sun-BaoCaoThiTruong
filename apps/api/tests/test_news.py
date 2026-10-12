from app.connectors.news import classify_event, relevance
from app.schemas import Security

HPG = Security(
    symbol="HPG",
    name="CTCP Tập đoàn Hòa Phát",
    aliases=["Hòa Phát", "Hoa Phat"],
    exchange="HOSE",
)


def test_vietnamese_alias_relevance_and_event_classification():
    assert relevance("Hòa Phát công bố lợi nhuận quý", HPG) >= 0.3
    assert relevance("Giá vàng thế giới tăng", HPG) == 0
    assert classify_event("Hòa Phát công bố kết quả kinh doanh") == "earnings"
