"use client";

import { FormEvent, useEffect, useState } from "react";
import type { Analysis, AnalystResponse, DataQualityReport, FinancialMetricResult, FinancialTrendResponse, ValuationResult } from "@/lib/types";
import { PriceChart } from "./PriceChart";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const money = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Không có";
}

export function Dashboard() {
  const [symbol, setSymbol] = useState("HPG");
  const [data, setData] = useState<Analysis | null>(null);
  const [fundamentals, setFundamentals] = useState<FinancialMetricResult | null>(null);
  const [financialTrend, setFinancialTrend] = useState<FinancialTrendResponse | null>(null);
  const [dcfResult, setDcfResult] = useState<ValuationResult | null>(null);
  const [dcfError, setDcfError] = useState("");
  const [dcfCashFlows, setDcfCashFlows] = useState("");
  const [dcfDiscountRate, setDcfDiscountRate] = useState("");
  const [dcfTerminalGrowth, setDcfTerminalGrowth] = useState("");
  const [dcfNetDebt, setDcfNetDebt] = useState("");
  const [dcfShares, setDcfShares] = useState("");
  const [analyst, setAnalyst] = useState<AnalystResponse | null>(null);
  const [quality, setQuality] = useState<DataQualityReport | null>(null);
  const [analystLoading, setAnalystLoading] = useState(false);
  const [newsSource, setNewsSource] = useState("");
  const [newsCategory, setNewsCategory] = useState("");
  const [newsFrom, setNewsFrom] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function fetchAnalysis(nextSymbol: string): Promise<Analysis> {
    const search = await fetch(`${API}/stocks/search?q=${encodeURIComponent(nextSymbol)}`, { cache: "no-store" });
    if (!search.ok) throw new Error("Không thể tra cứu securities master.");
    const matches: { symbol: string }[] = await search.json();
    if (!matches.length) throw new Error(`Không tìm thấy mã hoặc doanh nghiệp “${nextSymbol}”.`);
    const response = await fetch(`${API}/stocks/${encodeURIComponent(matches[0].symbol)}/analysis`, { cache: "no-store" });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail?.message ?? `API trả mã ${response.status}`);
    }
    return response.json();
  }

  async function fetchQuality() {
    const response = await fetch(`${API}/data-quality`, { cache: "no-store" });
    setQuality(response.ok ? await response.json() : null);
  }

  async function fetchFundamentals(nextSymbol: string) {
    const response = await fetch(`${API}/stocks/${encodeURIComponent(nextSymbol)}/fundamentals`, { cache: "no-store" });
    if (!response.ok) {
      setFundamentals(null);
      setFinancialTrend(null);
      return;
    }
    setFundamentals(await response.json());
    const history = await fetch(`${API}/stocks/${encodeURIComponent(nextSymbol)}/fundamentals/history?period_type=year&statement_scope=consolidated`, { cache: "no-store" });
    setFinancialTrend(history.ok ? await history.json() : null);
  }

  async function load(nextSymbol: string) {
    setLoading(true);
    setError("");
    try {
      const analysis = await fetchAnalysis(nextSymbol);
      setData(analysis);
      await fetchFundamentals(analysis.security.symbol);
      await fetchQuality();
    } catch (reason) {
      setData(null);
      setFundamentals(null);
      setFinancialTrend(null);
      setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAnalysis("HPG")
      .then(async (analysis) => {
        setData(analysis);
        await fetchFundamentals(analysis.security.symbol);
        await fetchQuality();
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu."))
      .finally(() => setLoading(false));
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (symbol.trim()) void load(symbol.trim());
  }

  async function downloadReport() {
    if (!data) return;
    const response = await fetch(`${API}/stocks/${data.security.symbol}/reports`, { method: "POST" });
    if (!response.ok) { setError("Không thể tạo báo cáo PDF lúc này."); return; }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${data.security.symbol}-research-report.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function askAnalyst() {
    if (!data) return;
    setAnalystLoading(true);
    try {
      const response = await fetch(`${API}/analyst/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol: data.security.symbol, question: "Tóm tắt dữ liệu hiện có, rủi ro và điều kiện cần theo dõi." }) });
      setAnalyst(response.ok ? await response.json() : { status: "unavailable", symbol: data.security.symbol, answer: "Không thể gọi analyst lúc này.", sections: {}, limitations: [] });
    } finally { setAnalystLoading(false); }
  }

  async function calculateDcf(event: FormEvent) {
    event.preventDefault();
    if (!data) return;
    const cashFlows = dcfCashFlows.split(",").map((value) => Number(value.trim())).filter((value) => Number.isFinite(value));
    const discountRate = Number(dcfDiscountRate) / 100;
    const terminalGrowthRate = Number(dcfTerminalGrowth) / 100;
    const shares = Number(dcfShares);
    if (!cashFlows.length || !Number.isFinite(discountRate) || !Number.isFinite(terminalGrowthRate) || !Number.isFinite(shares) || shares <= 0) {
      setDcfError("Nhập đầy đủ dòng tiền, tỷ lệ chiết khấu, tăng trưởng dài hạn và số cổ phiếu.");
      return;
    }
    setDcfError("");
    const response = await fetch(`${API}/fundamentals/valuation/dcf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: data.security.symbol,
        forecast_free_cash_flows: cashFlows,
        discount_rate: discountRate,
        terminal_growth_rate: terminalGrowthRate,
        net_debt: Number(dcfNetDebt) || 0,
        shares_outstanding: shares,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setDcfResult(null);
      setDcfError(payload?.detail?.[0]?.msg ?? "Giả định DCF không hợp lệ. Tăng trưởng dài hạn phải thấp hơn tỷ lệ chiết khấu.");
      return;
    }
    setDcfResult(await response.json());
  }

  const indicators = data ? ["sma20", "sma50", "rsi14", "macd", "atr14", "max_drawdown"] : [];
  const filteredNews = data?.news.filter((item) => {
    if (newsSource && item.publisher !== newsSource) return false;
    if (newsCategory && item.event_category !== newsCategory) return false;
    if (newsFrom && (!item.published_at || new Date(item.published_at) < new Date(newsFrom))) return false;
    return true;
  }) ?? [];
  return <main>
    <header className="topbar">
      <a className="brand" href="#top" aria-label="Mạch Thị Trường — trang đầu">Mạch<span>/</span>Thị Trường</a>
      <nav aria-label="Điều hướng chính"><a href="#research">Nghiên cứu</a><a href="#news">Tin liên quan</a><a href="#sources">Nguồn dữ liệu</a></nav>
      <span className="read-only">CHỈ ĐỌC · KHÔNG GIAO DỊCH</span>
    </header>

    <section className="query-strip" id="top">
      <div><p className="eyebrow">Bàn nghiên cứu cổ phiếu Việt Nam</p><h1>Đi từ dữ liệu đến luận điểm.</h1></div>
      <form onSubmit={submit} aria-label="Tìm mã cổ phiếu">
        <label htmlFor="symbol">Mã chứng khoán</label>
        <div className="search-row"><input id="symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} maxLength={10} autoComplete="off" /><button className={loading ? "is-loading" : ""} disabled={loading}>{loading ? "Đang tải…" : "Phân tích →"}</button></div>
        <small>Tìm theo mã, tên doanh nghiệp hoặc bí danh trong securities master.</small>
      </form>
    </section>

    {loading && <section className="state-panel" role="status"><span className="loader" />Đang truy xuất và tính toán chỉ báo…</section>}
    {error && <section className="state-panel error" role="alert"><strong>Chưa thể hoàn tất nghiên cứu.</strong><p>{error}</p><button onClick={() => void load(symbol)}>Thử lại</button></section>}

    {data && !loading && <>
      {data.prices.provenance.mode === "fixture" && <aside className="fixture-warning">DỮ LIỆU FIXTURE — chỉ dùng kiểm thử, không phải dữ liệu thị trường.</aside>}
      <section className="market-head" id="research">
        <div><div className="symbol-line"><span className="ticker">{data.security.symbol}</span><span>{data.security.exchange}</span></div><h2>{data.security.name}</h2><p>Nguồn {data.prices.provenance.source} · cập nhật {formatDate(data.prices.provenance.market_timestamp)}</p></div>
        <div className="quote"><strong>{money.format(data.latest_price)}</strong><span className={(data.change_percent ?? 0) >= 0 ? "positive" : "negative"}>{data.change_percent === null ? "—" : `${data.change_percent >= 0 ? "+" : ""}${decimal.format(data.change_percent)}%`}</span><small>{data.security.currency} · dữ liệu trễ</small></div>
      </section>

      <section className="workbench-grid">
        <article className="panel chart-panel"><div className="panel-head"><div><p className="eyebrow">Giá đóng cửa</p><h3>120 phiên gần nhất</h3></div><span>{data.prices.bars.length} quan sát</span></div><PriceChart bars={data.prices.bars} /></article>
        <aside className="panel thesis"><p className="eyebrow">Tóm tắt có căn cứ</p><h3>Điều dữ liệu đang nói</h3><ol>{data.summary.map((item) => <li key={item}>{item}</li>)}</ol><button onClick={downloadReport}>Tải báo cáo PDF ↓</button></aside>
      </section>

      <section className="indicator-section"><div className="section-head"><div><p className="eyebrow">Máy tính kỹ thuật · {data.technicals.formula_version}</p><h2>Tín hiệu, không phải khuyến nghị.</h2></div><p>Tính lúc {formatDate(data.technicals.calculated_at)} trên {data.technicals.sample_size} phiên.</p></div><div className="indicator-grid">{indicators.map((key) => { const item = data.technicals.indicators[key]; return <article className="indicator" key={key}><div><span>{key.replace("max_drawdown", "Drawdown lớn nhất").toUpperCase()}</span><i className={item.signal}>{item.signal === "positive" ? "Tích cực" : item.signal === "negative" ? "Tiêu cực" : "Trung tính"}</i></div><strong>{item.value === null ? "—" : decimal.format(item.value)}</strong><p>{item.explanation}</p></article>; })}</div></section>

      <section className="score-section">
        <div className="section-head"><div><h2>Bốn chiều kỹ thuật độc lập</h2></div><p>Điểm 0–100 theo công thức technical-v2. Điểm rủi ro cao nghĩa là biến động và drawdown lớn hơn.</p></div>
        <div className="score-table">{Object.entries(data.technicals.component_scores).map(([key, value]) => <div key={key}><span>{key === "trend" ? "Xu hướng" : key === "momentum" ? "Động lượng" : key === "volume_confirmation" ? "Xác nhận khối lượng" : "Rủi ro biến động"}</span><strong>{value === null ? "Chưa đủ dữ liệu" : `${decimal.format(value)} / 100`}</strong></div>)}</div>
        {data.technicals.conflicts.length > 0 && <div className="conflict" role="note"><strong>Tín hiệu xung đột</strong>{data.technicals.conflicts.map((item) => <p key={item}>{item}</p>)}</div>}
      </section>

      <section className="fundamental-section">
        <div className="section-head"><div><p className="eyebrow">Phân tích cơ bản</p><h2>BCTC đã lưu trong hệ thống</h2></div><p>{fundamentals ? `Kỳ ${fundamentals.period_type ?? "không xác định"} · ${fundamentals.statement_scope === "separate" ? "riêng lẻ" : "hợp nhất"} · ${fundamentals.statement_status === "amended" ? "đã điều chỉnh" : "bản gốc"} · ${formatDate(fundamentals.period_end)} · nguồn ${fundamentals.source_name ?? "không rõ"}` : "Chưa có BCTC hợp lệ được kết nối cho mã này."}</p></div>
        {fundamentals ? <><div className="metric-grid">{[["Doanh thu tăng trưởng", "revenue_growth_percent", "%"], ["Lợi nhuận tăng trưởng", "net_income_growth_percent", "%"], ["ROE", "roe_percent", "%"], ["ROA", "roa_percent", "%"], ["Biên ròng", "net_margin_percent", "%"], ["D/E", "debt_to_equity", "x"], ["Current ratio", "current_ratio", "x"], ["EPS", "eps", ""], ["P/E", "pe", "x"]].map(([label, key, suffix]) => <article key={key}><span>{label}</span><strong>{fundamentals.metrics[key] === null || fundamentals.metrics[key] === undefined ? "—" : `${decimal.format(fundamentals.metrics[key] as number)}${suffix}`}</strong></article>)}</div><ul className="metric-warnings">{fundamentals.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></> : <div className="empty">Hãy nạp CSV BCTC được cấp phép qua endpoint quản trị để bật phân tích theo quý/năm. Không suy đoán số liệu còn thiếu.</div>}
        {financialTrend && <div className="financial-trend"><h3>Xu hướng BCTC năm · hợp nhất</h3><div className="trend-scroll"><table><thead><tr><th>Kỳ</th><th>Tăng trưởng DT</th><th>Tăng trưởng LN</th><th>ROE</th><th>Biên ròng</th><th>OCF</th></tr></thead><tbody>{financialTrend.periods.map((period) => <tr key={period.period_end}><td>{period.period_end ? new Date(period.period_end).getFullYear() : "—"}{period.statement_status === "amended" ? " · điều chỉnh" : ""}</td>{["revenue_growth_percent", "net_income_growth_percent", "roe_percent", "net_margin_percent", "operating_cash_flow"].map((key) => <td key={key}>{period.metrics[key] === null || period.metrics[key] === undefined ? "—" : decimal.format(period.metrics[key] as number)}</td>)}</tr>)}</tbody></table></div>{financialTrend.warnings.map((warning) => <small key={warning}>{warning}</small>)}</div>}
      </section>

      <section className="valuation-section">
        <div className="section-head"><div><h2>DCF với giả định minh bạch</h2></div><p>Công cụ chỉ tính từ các giả định bạn nhập; không tự tạo dự báo, benchmark hoặc khuyến nghị.</p></div>
        <form className="dcf-form" onSubmit={calculateDcf}>
          <label>Dòng tiền tự do dự báo<input value={dcfCashFlows} onChange={(event) => setDcfCashFlows(event.target.value)} placeholder="Ví dụ: 1000, 1150, 1300" inputMode="decimal" /></label>
          <label>Tỷ lệ chiết khấu (%)<input value={dcfDiscountRate} onChange={(event) => setDcfDiscountRate(event.target.value)} placeholder="Ví dụ: 12" inputMode="decimal" /></label>
          <label>Tăng trưởng dài hạn (%)<input value={dcfTerminalGrowth} onChange={(event) => setDcfTerminalGrowth(event.target.value)} placeholder="Ví dụ: 3" inputMode="decimal" /></label>
          <label>Nợ ròng<input value={dcfNetDebt} onChange={(event) => setDcfNetDebt(event.target.value)} placeholder="Cùng đơn vị với FCF" inputMode="decimal" /></label>
          <label>Số cổ phiếu lưu hành<input value={dcfShares} onChange={(event) => setDcfShares(event.target.value)} placeholder="Cùng thang đơn vị" inputMode="decimal" /></label>
          <button type="submit">Tính ba kịch bản DCF</button>
        </form>
        {dcfError && <p className="form-error" role="alert">{dcfError}</p>}
        {dcfResult && <div className="valuation-output"><p>Tính lúc {formatDate(dcfResult.calculated_at)} · đơn vị mỗi cổ phiếu phụ thuộc thang dữ liệu đầu vào.</p><dl>{["bull", "base", "bear"].map((scenario) => <div key={scenario}><dt>{scenario === "bull" ? "Tích cực" : scenario === "bear" ? "Tiêu cực" : "Cơ sở"}</dt><dd>{dcfResult.scenarios[scenario] === null ? "—" : decimal.format(dcfResult.scenarios[scenario] as number)}</dd></div>)}</dl><ul>{dcfResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
      </section>

      <section className="research-case">
        <div className="section-head"><div><h2>Luận điểm hai chiều</h2></div><p>{data.fundamental_message}</p></div>
        <div className="case-grid"><article><h3>Yếu tố hỗ trợ</h3>{data.bullish_factors.length ? <ul>{data.bullish_factors.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Chưa có yếu tố hỗ trợ đủ mạnh theo ngưỡng hiện tại.</p>}</article><article><h3>Yếu tố làm suy yếu</h3><ul>{data.bearish_factors.map((item) => <li key={item}>{item}</li>)}</ul></article></div>
        <div className="scenario-list">{Object.entries(data.scenarios).map(([name, lines]) => <article key={name}><span>{name === "bull" ? "Kịch bản tích cực" : name === "bear" ? "Kịch bản tiêu cực" : "Kịch bản cơ sở"}</span><ul>{lines.map((item) => <li key={item}>{item}</li>)}</ul></article>)}</div>
      </section>

      <section className="news-section" id="news"><div className="section-head"><div><p className="eyebrow">Tin liên quan</p><h2>Tiêu đề khớp từ RSS</h2></div><p>Metadata và liên kết gốc; không sao chép nội dung bài viết.</p></div>{data.news.length ? <><div className="news-filters"><label>Nguồn<select value={newsSource} onChange={(event) => setNewsSource(event.target.value)}><option value="">Tất cả nguồn</option>{Array.from(new Set(data.news.map((item) => item.publisher))).map((source) => <option key={source}>{source}</option>)}</select></label><label>Loại sự kiện<select value={newsCategory} onChange={(event) => setNewsCategory(event.target.value)}><option value="">Tất cả loại</option>{Array.from(new Set(data.news.map((item) => item.event_category))).map((category) => <option key={category}>{category}</option>)}</select></label><label>Từ ngày<input type="date" value={newsFrom} onChange={(event) => setNewsFrom(event.target.value)} /></label></div>{filteredNews.length ? <div className="news-list">{filteredNews.map((item) => <a key={item.url} href={item.url} target="_blank" rel="noreferrer"><span>{item.publisher} · {item.event_category} · {formatDate(item.published_at)}</span><strong>{item.title}</strong><b>Đọc nguồn ↗</b></a>)}</div> : <div className="empty">Không có bài nào khớp bộ lọc. Hãy mở rộng nguồn, loại sự kiện hoặc khoảng thời gian.</div>}</> : <div className="empty">Không tìm thấy tiêu đề RSS phù hợp trong cửa sổ hiện tại.</div>}</section>

      <section className="analyst-section"><div className="section-head"><div><p className="eyebrow">AI analyst có căn cứ</p><h2>Hỏi trên dữ liệu đã truy xuất</h2></div><button onClick={() => void askAnalyst()} disabled={analystLoading}>{analystLoading ? "Đang tổng hợp…" : "Tóm tắt có evidence"}</button></div>{analyst ? <><p>{analyst.answer}</p>{analyst.evidence && analyst.evidence.length > 0 && <div className="analyst-evidence">{analyst.evidence.map((item) => <article key={item.evidence_id}><span>{item.evidence_id} · {item.kind}</span><strong>{item.statement}</strong><small>{item.source ?? "Nguồn nội bộ"} · độ tin cậy {item.confidence}</small></article>)}</div>}{analyst.limitations.map((item) => <small key={item}>{item}</small>)}</> : <div className="empty">Không gửi dữ liệu người dùng hoặc bí mật tới trình duyệt; analyst chỉ dùng tool outputs nội bộ.</div>}</section>

      <section className="quality-section" id="sources">
        <div className="section-head"><div><h2>Chất lượng và độ phủ dữ liệu</h2></div><p>{quality ? `Ảnh chụp hệ thống lúc ${formatDate(quality.generated_at)}.` : "Không thể tải chẩn đoán nguồn trong lần truy cập này."}</p></div>
        {quality && <>
          <dl className="coverage-strip"><div><dt>Mã đang hoạt động</dt><dd>{quality.active_securities_count} / {quality.securities_count}</dd></div><div><dt>Quan sát giá đã lưu</dt><dd>{money.format(quality.price_observations_count)}</dd></div><div><dt>Mốc thị trường gần nhất</dt><dd>{formatDate(quality.last_market_timestamp)}</dd></div></dl>
          <div className="source-table" role="table" aria-label="Trạng thái nguồn dữ liệu">{quality.sources.map((source) => <article role="row" key={source.name}><div><strong>{source.name}</strong><span className={`source-state ${source.availability}`}>{source.availability === "available" ? "Sẵn sàng" : source.availability === "configured" ? "Đã cấu hình" : source.availability === "fixture" ? "Fixture" : "Chưa khả dụng"}</span></div><p>{source.capabilities.join(" · ")}</p><dl><div><dt>Thành công gần nhất</dt><dd>{formatDate(source.last_success_at)}</dd></div><div><dt>Thất bại gần nhất</dt><dd>{formatDate(source.last_failure_at)}</dd></div><div><dt>Độ mới</dt><dd>{source.freshness}</dd></div></dl>{source.message && <small>{source.message}</small>}</article>)}</div>
          {quality.issues.length > 0 && <div className="quality-issues"><strong>Các giới hạn cần xử lý</strong><ul>{quality.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
        </>}
      </section>

      <section className="evidence"><div><p className="eyebrow">Dấu vết bằng chứng</p><h2>{data.evidence_count} mục dữ liệu hỗ trợ</h2></div><dl><div><dt>Chế độ</dt><dd>{data.prices.provenance.mode}</dd></div><div><dt>Truy xuất</dt><dd>{formatDate(data.prices.provenance.retrieved_at)}</dd></div><div><dt>Điều chỉnh giá</dt><dd>Chưa xác nhận đầy đủ</dd></div></dl><ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>
    </>}
    <footer><span>Mạch Thị Trường · V4</span><span>Nghiên cứu hỗ trợ quyết định, không phải tư vấn đầu tư.</span></footer>
  </main>;
}

