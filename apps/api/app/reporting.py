from io import BytesIO
from html import escape
from os import environ
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import AnalysisResponse


def _register_vietnamese_font() -> str:
    """Require a Unicode TrueType font instead of silently corrupting Vietnamese text."""
    paths = [
        environ.get("PDF_FONT_PATH", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for value in paths:
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_file():
            name = "MarketReportUnicode"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(candidate)))
            return name
    raise RuntimeError(
        "Vietnamese PDF font missing. Install fonts-dejavu-core or set PDF_FONT_PATH "
        "to a Unicode TrueType (.ttf) font."
    )


def _para(value: object, style):
    return Paragraph(escape(str(value), quote=True), style)


def build_pdf(analysis: AnalysisResponse) -> bytes:
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    font_name = _register_vietnamese_font()
    for style in styles.byName.values():
        style.fontName = font_name
    story = [
        _para(f"Báo cáo nghiên cứu — {analysis.security.symbol}", styles["Title"]),
        _para(analysis.security.name, styles["Heading2"]),
        _para(f"Thời điểm tạo: {analysis.generated_at.isoformat()}", styles["BodyText"]),
        Spacer(1, 8),
        Table(
            [[_para(cell, styles["BodyText"]) for cell in row] for row in [
                ["Giá gần nhất", f"{analysis.latest_price:,.0f} {analysis.security.currency}"],
                [
                    "Biến động",
                    "—" if analysis.change_percent is None else f"{analysis.change_percent:+.2f}%",
                ],
                ["Nguồn", analysis.prices.provenance.source],
                ["Thời điểm thị trường", str(analysis.prices.provenance.market_timestamp)],
                ["Chế độ dữ liệu", analysis.prices.provenance.mode.upper()],
                ["Kiểm định OHLCV", analysis.prices.provenance.validation_status],
            ]],
            colWidths=[45 * mm, 115 * mm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        ),
        Spacer(1, 12),
        _para("Tóm tắt dựa trên bằng chứng", styles["Heading2"]),
    ]
    story.extend(_para(f"• {line}", styles["BodyText"]) for line in analysis.summary)
    story += [Spacer(1, 12), _para("Chỉ báo kỹ thuật", styles["Heading2"])]
    rows = [["Chỉ báo", "Giá trị", "Tín hiệu"]]
    for key in ("sma20", "sma50", "rsi14", "macd", "atr14", "max_drawdown"):
        item = analysis.technicals.indicators[key]
        rows.append([key.upper(), "—" if item.value is None else f"{item.value:,.4f}", item.signal])
    story.append(
        Table(
            [[_para(cell, styles["BodyText"]) for cell in row] for row in rows],
            colWidths=[55 * mm, 55 * mm, 50 * mm],
            repeatRows=1,
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ]
            ),
        )
    )
    story += [Spacer(1, 12), _para("Luận điểm tích cực", styles["Heading2"])]
    story.extend(_para(f"• {line}", styles["BodyText"]) for line in analysis.bullish_factors)
    story += [Spacer(1, 12), _para("Luận điểm tiêu cực", styles["Heading2"])]
    story.extend(_para(f"• {line}", styles["BodyText"]) for line in analysis.bearish_factors)
    story += [Spacer(1, 12), _para("Kịch bản", styles["Heading2"])]
    for scenario, lines in analysis.scenarios.items():
        story.append(_para(scenario.upper(), styles["Heading3"]))
        story.extend(_para(f"• {line}", styles["BodyText"]) for line in lines)
    story += [Spacer(1, 12), _para("Giới hạn dữ liệu", styles["Heading2"])]
    story.extend(_para(f"• {line}", styles["BodyText"]) for line in analysis.limitations)
    document.build(story)
    return stream.getvalue()
