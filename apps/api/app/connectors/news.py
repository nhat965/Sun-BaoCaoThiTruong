"""Safe metadata-only news connectors. Article bodies are never fetched or executed."""
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Protocol
from xml.etree import ElementTree

import httpx

from app.schemas import NewsItem, Security
from app.text import normalize_vietnamese

EVENT_KEYWORDS = {
    "earnings": ("lợi nhuận", "doanh thu", "kết quả kinh doanh", "báo cáo tài chính"),
    "dividend": ("cổ tức", "tạm ứng cổ tức"),
    "capital_raising": ("phát hành", "tăng vốn", "chào bán"),
    "merger_acquisition": ("sáp nhập", "mua lại", "thâu tóm"),
    "leadership": ("bổ nhiệm", "miễn nhiệm", "chủ tịch", "tổng giám đốc"),
    "legal": ("khởi tố", "xử phạt", "thanh tra", "kiện"),
    "investment": ("dự án", "đầu tư", "nhà máy"),
}

def classify_event(title: str) -> str:
    normalized = normalize_vietnamese(title)
    for category, keywords in EVENT_KEYWORDS.items():
        if any(normalize_vietnamese(keyword) in normalized for keyword in keywords):
            return category
    return "other"

def relevance(title: str, security: Security) -> float:
    normalized = normalize_vietnamese(title)
    words = set(normalized.replace("-", " ").split())
    symbol_match = security.symbol.lower() in words
    alias_hits = sum(normalize_vietnamese(alias) in normalized for alias in [security.name, *security.aliases] if len(alias) > 3)
    return round(min(1.0, (0.7 if symbol_match else 0) + min(0.3, alias_hits * 0.15)), 3)

def group_hash(title: str, published_at: datetime | None) -> str:
    day = published_at.date().isoformat() if published_at else "unknown"
    return sha256(f"{normalize_vietnamese(title)}|{day}".encode()).hexdigest()

class NewsConnector(Protocol):
    name: str
    feed_url: str
    async def related(self, security: Security, limit: int = 8) -> list[NewsItem]: ...

class RssNewsConnector:
    def __init__(self, name: str, feed_url: str, timeout: float = 12) -> None:
        self.name, self.feed_url, self.timeout = name, feed_url, timeout

    async def related(self, security: Security, limit: int = 8) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(self.feed_url, headers={"User-Agent": "market-intelligence/0.3"})
                response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError):
            return []
        retrieved = datetime.now(UTC)
        matches: list[NewsItem] = []
        seen: set[str] = set()
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            if not title:
                continue
            normalized = normalize_vietnamese(title)
            if normalized in seen:
                continue
            score = relevance(title, security)
            if score < 0.3:
                continue
            seen.add(normalized)
            published = None
            if raw_date := node.findtext("pubDate"):
                try:
                    published = parsedate_to_datetime(raw_date).astimezone(UTC)
                except (TypeError, ValueError, OverflowError):
                    pass
            category = classify_event(title)
            link = node.findtext("link") or self.feed_url
            matches.append(NewsItem(title=title, publisher=self.name, published_at=published,
                url=link, related_symbols=[security.symbol], relevance_score=score,
                event_category=category, source_credibility="established_media", source_url=self.feed_url,
                retrieved_at=retrieved, event_summary=f"Sự kiện phân loại tự động: {category}.",
                facts=[f"Tiêu đề được xuất bản bởi {self.name}."],
                implications=["Cần đọc nguồn gốc và xác minh trước khi sử dụng trong quyết định."],
                uncertainty=["Chỉ dùng metadata RSS; không suy diễn toàn văn bài viết."], evidence=[link]))
            if len(matches) >= limit:
                break
        return matches

class VnExpressRssConnector(RssNewsConnector):
    name = "VnExpress Kinh doanh RSS"
    feed_url = "https://vnexpress.net/rss/kinh-doanh.rss"
    def __init__(self, timeout: float = 12) -> None:
        super().__init__(self.name, self.feed_url, timeout)
