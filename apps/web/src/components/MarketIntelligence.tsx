"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

type Breadth = { data_status: string; market_session: string | null; as_of: string | null; advancers: number | null; decliners: number | null; unchanged: number | null; above_ma20_percent: number | null; advance_decline_difference: number | null; limitations: string[] };
type Regime = { regime: string; evidence: string[]; conflicting_signals: string[]; limitations: string[] };
type Liquidity = { data_status: string; relative_volume: number | null; total_volume: number | null; top10_volume_share_percent: number | null; decline_heavy_volume_count: number | null; volume_expansion_count: number | null; limitations: string[] };
type Risk = { data_status: string; market_session: string | null; as_of: string | null; signals: { signal_id: string; signal_type: string; severity: string; title: string; trigger: Record<string, string | number | boolean | null>; evidence: string[]; limitations: string[] }[]; limitations: string[] };
type Scenarios = { data_status: string; scenarios: { scenario_id: string; label: string; horizon: string; assumptions: string[]; evidence: string[]; invalidation_conditions: string[]; risks: string[]; watch: string[]; status: string }[]; limitations: string[] };

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json() as Promise<T>;
}

export function MarketIntelligence() {
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [regime, setRegime] = useState<Regime | null>(null);
  const [liquidity, setLiquidity] = useState<Liquidity | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [scenarios, setScenarios] = useState<Scenarios | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [nextBreadth, nextRegime, nextLiquidity, nextRisk, nextScenarios] = await Promise.all([
        get<Breadth>("/market/breadth"),
        get<Regime>("/market/regime"),
        get<Liquidity>("/market/liquidity"),
        get<Risk>("/market/risks"),
        get<Scenarios>("/market/scenarios"),
      ]);
      setBreadth(nextBreadth); setRegime(nextRegime); setLiquidity(nextLiquidity); setRisk(nextRisk); setScenarios(nextScenarios);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tải market intelligence.");
    } finally { setLoading(false); }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const asOf = risk?.as_of ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(risk.as_of)) : "Chưa có timestamp";
  return <section className="market-intelligence" id="market-intelligence">
    <div className="section-head"><div><p className="eyebrow">Market intelligence · dữ liệu backend</p><h2>Bức tranh thị trường</h2></div><div className="market-intel-meta"><span className={`data-badge ${risk?.data_status ?? "unavailable"}`}>{risk?.data_status ?? (loading ? "đang tải" : "unavailable")}</span><small>As of {asOf}</small></div></div>
    {loading && <div className="state-panel" role="status"><span className="loader" />Đang tải breadth, regime, thanh khoản và cảnh báo…</div>}
    {error && <div className="state-panel error" role="alert"><strong>Không tải được market intelligence.</strong><p>{error}</p><button onClick={() => void load()}>Thử lại</button></div>}
    {!loading && !error && <>
      <div className="market-intel-grid">
        <article className="intel-card"><span>Regime</span><strong>{regime?.regime ?? "Chưa có dữ liệu"}</strong><small>{regime?.evidence?.[0] ?? "Chưa đủ bằng chứng."}</small></article>
        <article className="intel-card"><span>A/D difference</span><strong>{breadth?.advance_decline_difference ?? "Chưa có dữ liệu"}</strong><small>{breadth ? `${breadth.advancers ?? "—"} tăng · ${breadth.decliners ?? "—"} giảm · ${breadth.unchanged ?? "—"} đứng giá` : "Chưa đủ dữ liệu."}</small></article>
        <article className="intel-card"><span>Trên MA20</span><strong>{breadth?.above_ma20_percent === null || breadth?.above_ma20_percent === undefined ? "Chưa có dữ liệu" : `${breadth.above_ma20_percent}%`}</strong><small>Mẫu số được trả trong API breadth.</small></article>
        <article className="intel-card"><span>Relative volume</span><strong>{liquidity?.relative_volume === null || liquidity?.relative_volume === undefined ? "Chưa có dữ liệu" : `${liquidity.relative_volume}x`}</strong><small>Không suy diễn giá trị giao dịch khi nguồn thiếu.</small></article>
      </div>
      <div className="market-intel-columns">
        <article className="intel-panel"><div className="panel-head"><div><p className="eyebrow">Risk signals</p><h3>{risk?.signals.length ?? 0} cảnh báo có bằng chứng</h3></div><span>{risk?.market_session ?? "—"}</span></div>{risk?.signals.length ? <div className="risk-list">{risk.signals.map((signal) => <details key={signal.signal_id} open={signal.severity === "warning"}><summary><span className={`severity ${signal.severity}`}>{signal.severity}</span>{signal.title}</summary><p>{signal.evidence.join(" ")}</p><code>{JSON.stringify(signal.trigger)}</code></details>)}</div> : <p className="muted">Chưa có cảnh báo được kích hoạt từ dữ liệu hiện tại.</p>}{risk?.limitations.map((item) => <small className="limitation" key={item}>{item}</small>)}</article>
        <article className="intel-panel"><div className="panel-head"><div><p className="eyebrow">Liquidity & breadth</p><h3>Độ rộng và thanh khoản</h3></div><span>{liquidity?.data_status ?? "—"}</span></div><dl className="intel-dl"><div><dt>Volume phiên</dt><dd>{liquidity?.total_volume ?? "Chưa có dữ liệu"}</dd></div><div><dt>Top 10 volume share</dt><dd>{liquidity?.top10_volume_share_percent == null ? "Chưa có dữ liệu" : `${liquidity.top10_volume_share_percent}%`}</dd></div><div><dt>Mã giảm + volume lớn</dt><dd>{liquidity?.decline_heavy_volume_count ?? "Chưa có dữ liệu"}</dd></div><div><dt>Mã mở rộng volume</dt><dd>{liquidity?.volume_expansion_count ?? "Chưa có dữ liệu"}</dd></div></dl><div className="regime-note">{regime?.conflicting_signals.length ? `Xung đột: ${regime.conflicting_signals.join(" ")}` : "Chưa ghi nhận xung đột regime."}</div></article>
      </div>
      <div className="scenario-list market-scenarios"><div className="section-head"><div><p className="eyebrow">Scenario engine</p><h3>Điều kiện cần theo dõi</h3></div><small>Không có xác suất hay mục tiêu giá chưa được hiệu chỉnh.</small></div>{scenarios?.scenarios.map((scenario) => <article key={scenario.scenario_id}><span>{scenario.scenario_id} · {scenario.horizon}</span><h4>{scenario.label}</h4><strong>Giả định</strong><ul>{scenario.assumptions.map((item) => <li key={item}>{item}</li>)}</ul><strong>Phủ định khi</strong><ul>{scenario.invalidation_conditions.map((item) => <li key={item}>{item}</li>)}</ul><small className="muted">Theo dõi: {scenario.watch.join(" · ")}</small></article>)}</div>
      <div className="market-limitations"><strong>Giới hạn dữ liệu</strong><p>{[...(breadth?.limitations ?? []), ...(liquidity?.limitations ?? []), ...(risk?.limitations ?? []), ...(scenarios?.limitations ?? [])].filter((item, index, all) => all.indexOf(item) === index).slice(0, 6).join(" ") || "Không có giới hạn được trả về."}</p></div>
    </>}
  </section>;
}
