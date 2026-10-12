import json
from datetime import UTC, datetime

from app.analytics.technical import calculate_snapshot, percentage_change
from app.config import Settings
from app.connectors.manager import ConnectorManager
from app.connectors.news import RssNewsConnector, VnExpressRssConnector
from app.database import AnalysisRun, SessionLocal
from app.normalization import normalize_price_series
from app.repositories import NewsRepository, PriceRepository
from app.schemas import AnalysisResponse, PriceSeries


class AnalysisService:
    def __init__(self, settings: Settings) -> None:
        self.manager = ConnectorManager(settings)
        feeds = [feed.strip() for feed in settings.news_feeds.split(",") if feed.strip()]
        self.news_connectors = [
            VnExpressRssConnector(settings.request_timeout_seconds)
            if feed == VnExpressRssConnector.feed_url
            else RssNewsConnector(feed, feed, settings.request_timeout_seconds)
            for feed in feeds
        ]
        self.fixture_mode = settings.market_data_mode == "fixture"

    async def prices(self, symbol: str, limit: int = 260) -> PriceSeries:
        series = normalize_price_series(await self.manager.prices(symbol, limit))
        with SessionLocal() as session:
            PriceRepository(session).upsert_series(series)
            session.commit()
        return series

    async def analyze(self, symbol: str) -> AnalysisResponse:
        prices = await self.prices(symbol)
        bars = prices.bars
        technicals = calculate_snapshot(bars)
        news = [] if self.fixture_mode else await self.related_news(prices.security)
        previous = bars[-2].close if len(bars) > 1 else None
        change = percentage_change(bars[-1].close, previous) if previous is not None else None
        scores = technicals.component_scores
        trend = scores.get("trend")
        momentum = scores.get("momentum")
        volume = scores.get("volume_confirmation")
        risk = scores.get("volatility_risk")
        score_summary = ", ".join(
            f"{label} {value:.0f}/100"
            for label, value in (
                ("xu hướng", trend),
                ("động lượng", momentum),
                ("xác nhận khối lượng", volume),
                ("rủi ro biến động", risk),
            )
            if value is not None
        )
        bullish_factors = []
        bearish_factors = []
        if trend is not None:
            (bullish_factors if trend >= 60 else bearish_factors if trend <= 40 else []).append(
                f"Điểm xu hướng {trend:.0f}/100."
            )
        if momentum is not None:
            (
                bullish_factors if momentum >= 60 else bearish_factors if momentum <= 40 else []
            ).append(f"Điểm động lượng {momentum:.0f}/100.")
        if volume is not None and volume >= 60:
            bullish_factors.append(f"Khối lượng xác nhận ở mức {volume:.0f}/100.")
        if risk is not None and risk >= 60:
            bearish_factors.append(f"Rủi ro biến động ở mức {risk:.0f}/100.")
        bearish_factors.append(
            "Chưa có báo cáo tài chính đã xác minh để đánh giá nền tảng doanh nghiệp."
        )
        summary = [
            f"Giá gần nhất là {bars[-1].close:,.0f} {prices.security.currency}; biến động phiên gần nhất {change:+.2f}%."
            if change is not None
            else f"Giá gần nhất là {bars[-1].close:,.0f} {prices.security.currency}.",
            f"Điểm thành phần kỹ thuật: {score_summary or 'chưa đủ dữ liệu'}. Không cộng phiếu BUY/SELL đơn giản.",
            f"Có {len(news)} tiêu đề RSS khớp từ khóa; đây không phải đánh giá đầy đủ toàn bộ tin tức thị trường.",
        ]
        summary.extend(technicals.conflicts)
        result = AnalysisResponse(
            security=prices.security,
            latest_price=bars[-1].close,
            previous_close=previous,
            change_percent=change,
            prices=prices,
            technicals=technicals,
            news=news,
            summary=summary,
            limitations=[
                "Nguồn giá phát triển không phải feed thương mại được cấp phép riêng.",
                "Giá chưa được điều chỉnh đầy đủ cho mọi corporate action.",
                "Phân tích kỹ thuật mô tả dữ liệu quá khứ, không bảo đảm kết quả đầu tư.",
            ],
            generated_at=datetime.now(UTC),
            evidence_count=len(bars) + len(news),
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            scenarios={
                "bull": [
                    "Cần điểm xu hướng và động lượng duy trì trên 60 cùng xác nhận khối lượng.",
                    "Kịch bản mất hiệu lực nếu giá phá vùng hỗ trợ 20 phiên với khối lượng cao.",
                ],
                "base": [
                    "Theo dõi tín hiệu xung đột và chờ dữ liệu cơ bản được xác minh.",
                    "Không giả định mục tiêu giá khi chưa có mô hình định giá.",
                ],
                "bear": [
                    "Rủi ro tăng nếu xu hướng và động lượng cùng dưới 40.",
                    "Biến động cao hoặc breakdown vùng hỗ trợ là điều kiện cần giám sát.",
                ],
            },
        )
        with SessionLocal() as session:
            session.add(
                AnalysisRun(
                    symbol=prices.security.symbol,
                    status="completed",
                    formula_version=technicals.formula_version,
                    source_name=prices.provenance.source,
                    coverage=f"{len(bars)} bars",
                    provenance_json=json.dumps(prices.provenance.model_dump(mode="json")),
                    created_at=result.generated_at,
                )
            )
            session.commit()
        return result

    async def related_news(self, security, limit: int = 20):
        if self.fixture_mode:
            return []
        combined = []
        for connector in self.news_connectors:
            combined.extend(await connector.related(security, limit=limit))
        dedup = {}
        for item in combined:
            dedup[(item.publisher, str(item.url))] = item
        items = sorted(dedup.values(), key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)[:limit]
        with SessionLocal() as session:
            NewsRepository(session).store(security.symbol, items)
        return items
