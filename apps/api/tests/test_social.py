from app.schemas import SocialBatchRequest, SocialContentItem
from app.social import analyze_social_batch


def test_vietnamese_social_batch_reports_sampling_and_uncertainty():
    result = analyze_social_batch(
        SocialBatchRequest(
            items=[
                SocialContentItem(
                    symbol="HPG",
                    content="Nghe nói lợi nhuận tăng mạnh, nhưng rủi ro vẫn cao?",
                ),
                SocialContentItem(symbol="HPG", content="Nội dung không có tín hiệu rõ ràng"),
            ]
        )
    )
    assert result.sample_size == 2
    assert result.items[0].sentiment == "mixed"
    assert result.items[0].content_type == "rumor"
    assert result.items[1].sentiment == "uncertain"
    assert "không đại diện" in result.coverage_note
