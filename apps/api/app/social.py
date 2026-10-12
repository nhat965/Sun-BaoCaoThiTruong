"""Transparent Vietnamese classification for authorized user-supplied discussion text."""

from collections import Counter
from datetime import UTC, datetime

from app.schemas import (
    SocialBatchRequest,
    SocialBatchResult,
    SocialClassification,
    SocialContentItem,
)
from app.text import normalize_vietnamese

POSITIVE = {"tang truong", "tich cuc", "vuot dinh", "loi nhuan tang", "breakout"}
NEGATIVE = {"rui ro", "tieu cuc", "thua lo", "lo", "giam manh", "breakdown"}
TYPE_TERMS = {
    "rumor": {"tin don", "nghe noi", "chua xac minh"},
    "promotional": {"room vip", "cam ket loi", "mua ngay", "x2 tai khoan"},
    "question": {"?", "cho hoi", "the nao"},
    "forecast": {"du bao", "muc tieu", "se tang", "se giam"},
    "technical_opinion": {"khang cu", "ho tro", "rsi", "breakout", "breakdown"},
    "fundamental_opinion": {"doanh thu", "loi nhuan", "roe", "bctc", "dong tien"},
}


def classify_social_item(item: SocialContentItem) -> SocialClassification:
    normalized = normalize_vietnamese(item.content)
    positive = sorted(term for term in POSITIVE if term in normalized)
    negative = sorted(term for term in NEGATIVE if term in normalized)
    if positive and negative:
        sentiment = "mixed"
    elif positive:
        sentiment = "positive"
    elif negative:
        sentiment = "negative"
    elif any(term in normalized for term in ("trung lap", "khong doi")):
        sentiment = "neutral"
    else:
        sentiment = "uncertain"
    content_type = "other"
    type_matches = []
    for candidate, terms in TYPE_TERMS.items():
        matches = sorted(term for term in terms if term in normalized)
        if matches:
            content_type = candidate
            type_matches = matches
            break
    matched = sorted(set(positive + negative + type_matches))
    uncertainty = [
        "Phân loại từ khóa xác định; không xác minh tính đúng sai của nội dung.",
        "Mẫu do người dùng cung cấp không đại diện toàn bộ nhà đầu tư.",
    ]
    if sentiment == "uncertain":
        uncertainty.append("Không có đủ tín hiệu từ vựng để xác định cảm xúc.")
    return SocialClassification(
        symbol=item.symbol.strip().upper(),
        sentiment=sentiment,
        content_type=content_type,
        confidence="medium" if len(matched) >= 2 else "low",
        matched_terms=matched,
        source_name=item.source_name,
        published_at=item.published_at,
        uncertainty=uncertainty,
    )


def analyze_social_batch(payload: SocialBatchRequest) -> SocialBatchResult:
    items = [classify_social_item(item) for item in payload.items]
    return SocialBatchResult(
        sample_size=len(items),
        sentiment_distribution=dict(Counter(item.sentiment for item in items)),
        type_distribution=dict(Counter(item.content_type for item in items)),
        items=items,
        coverage_note=(
            "Chỉ phản ánh batch nội dung được người dùng cấp quyền cung cấp; "
            "không đại diện toàn bộ cộng đồng nhà đầu tư."
        ),
        generated_at=datetime.now(UTC),
    )
