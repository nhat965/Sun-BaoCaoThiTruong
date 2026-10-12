from datetime import UTC
from email.utils import parsedate_to_datetime
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
    symbol_match = security.symbol.lower() in normalized.split()
    aliases = [security.name, *security.aliases]
    alias_hits = sum(
        normalize_vietnamese(alias) in normalized for alias in aliases if len(alias) > 3
    )
    score = (0.7 if symbol_match else 0) + min(0.3, alias_hits * 0.15)
    return round(min(1.0, score), 3)


class VnExpressRssConnector:
    name = "VnExpress Kinh doanh RSS"
    feed_url = "https://vnexpress.net/rss/kinh-doanh.rss"

    def __init__(self, timeout: float = 12) -> None:
        self.timeout = timeout

    async def related(self, security: Security, limit: int = 8) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.feed_url, headers={"User-Agent": "market-intelligence-mvp/0.2"}
                )
                response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError):
            return []
        matches: list[NewsItem] = []
        seen_titles: set[str] = set()
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            normalized_title = normalize_vietnamese(title)
            if normalized_title in seen_titles:
                continue
            score = relevance(title, security)
            if score < 0.3:
                continue
            seen_titles.add(normalized_title)
            published = None
            if raw_date := node.findtext("pubDate"):
                try:
                    published = parsedate_to_datetime(raw_date).astimezone(UTC)
                except (TypeError, ValueError):
                    pass
            matches.append(
                NewsItem(
                    title=title,
                    publisher="VnExpress",
                    published_at=published,
                    url=node.findtext("link") or self.feed_url,
                    related_symbols=[security.symbol],
                    relevance_score=score,
                    event_category=classify_event(title),
                    source_credibility="established_media",
                )
            )
            if len(matches) >= limit:
                break
        return matches
