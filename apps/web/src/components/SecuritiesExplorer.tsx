"use client";

import { useEffect, useState } from "react";
import type { SecuritiesExplorerItem, SecuritiesExplorerResponse } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const integer = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });
const WATCHLIST_KEY = "market-intelligence:watchlist";

type SortKey = "symbol" | "name" | "price" | "change" | "volume";
type SortOrder = "asc" | "desc";

const statusLabels: Record<string, string> = {
  active: "Đang niêm yết",
  inactive: "Ngừng hoạt động",
  delisted: "Hủy niêm yết",
  suspended: "Tạm ngừng",
};

function MissingValue() {
  return <span className="missing-value">Chưa có dữ liệu</span>;
}

function formatDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(
        new Date(value),
      )
    : null;
}

function formatTradingValue(value: number | null) {
  if (value === null) return null;
  if (Math.abs(value) >= 1_000_000_000) return `${decimal.format(value / 1_000_000_000)} tỷ`;
  if (Math.abs(value) >= 1_000_000) return `${decimal.format(value / 1_000_000)} triệu`;
  return integer.format(value);
}

function PinIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="m12 3 2.72 5.52 6.09.88-4.4 4.29 1.04 6.06L12 16.89l-5.45 2.86 1.04-6.06-4.4-4.29 6.09-.88L12 3Z"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SecuritiesExplorer({
  activeSymbol,
  onAnalyze,
}: {
  activeSymbol: string;
  onAnalyze: (symbol: string) => void;
}) {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [exchange, setExchange] = useState("");
  const [sector, setSector] = useState("");
  const [listingStatus, setListingStatus] = useState("active");
  const [sortBy, setSortBy] = useState<SortKey>("symbol");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [result, setResult] = useState<SecuritiesExplorerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [pinned, setPinned] = useState<string[]>([]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(searchInput.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const stored = JSON.parse(window.localStorage.getItem(WATCHLIST_KEY) ?? "[]");
        if (Array.isArray(stored)) setPinned(stored.filter((item) => typeof item === "string"));
      } catch {
        window.localStorage.removeItem(WATCHLIST_KEY);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    if (query) params.set("q", query);
    if (exchange) params.set("exchange", exchange);
    if (sector) params.set("sector", sector);
    if (listingStatus) params.set("listing_status", listingStatus);
    async function loadSecurities() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API}/securities?${params}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`API trả mã ${response.status}`);
        setResult((await response.json()) as SecuritiesExplorerResponse);
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Không thể tải danh mục chứng khoán.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void loadSecurities();
    return () => controller.abort();
  }, [exchange, listingStatus, page, pageSize, query, reloadKey, sector, sortBy, sortOrder]);

  function updateFilter(setter: (value: string) => void, value: string) {
    setter(value);
    setPage(1);
  }

  function changeSort(nextSort: SortKey) {
    if (sortBy === nextSort) setSortOrder((current) => (current === "asc" ? "desc" : "asc"));
    else {
      setSortBy(nextSort);
      setSortOrder("asc");
    }
    setPage(1);
  }

  function togglePinned(symbol: string) {
    setPinned((current) => {
      const next = current.includes(symbol)
        ? current.filter((item) => item !== symbol)
        : [...current, symbol];
      window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(next));
      return next;
    });
  }

  function sortButton(label: string, value: SortKey, tooltip?: string) {
    return (
      <button
        type="button"
        className={sortBy === value ? "table-sort is-active" : "table-sort"}
        onClick={() => changeSort(value)}
        title={tooltip}
      >
        <span>{label}</span>
        <i className={sortBy === value && sortOrder === "desc" ? "sort-mark desc" : "sort-mark"} />
      </button>
    );
  }

  const items = result?.items ?? [];
  return (
    <section className="explorer" id="securities" aria-labelledby="explorer-heading">
      <div className="explorer-intro">
        <div>
          <h1 id="explorer-heading">Danh mục chứng khoán, nhìn từ dữ liệu.</h1>
          <p>
            Khám phá doanh nghiệp theo sàn và ngành. Registry hiện phản ánh đúng nguồn đã nhập;
            ô trống không được thay bằng số ước đoán.
          </p>
        </div>
        <dl className="explorer-status">
          <div><dt>Mã phù hợp</dt><dd>{result ? integer.format(result.total) : "—"}</dd></div>
          <div><dt>Đã ghim</dt><dd>{pinned.length}</dd></div>
          <div><dt>API cập nhật</dt><dd>{result ? formatDate(result.generated_at) : "—"}</dd></div>
        </dl>
      </div>

      <div className="explorer-controls" aria-label="Bộ lọc danh mục">
        <label className="explorer-search">
          Tìm mã hoặc doanh nghiệp
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Ví dụ: HPG hoặc Hoa Phat"
            autoComplete="off"
          />
        </label>
        <label>
          Sàn giao dịch
          <select value={exchange} onChange={(event) => updateFilter(setExchange, event.target.value)}>
            <option value="">Tất cả sàn</option>
            {(result?.available_exchanges ?? ["HOSE", "HNX", "UPCOM"]).map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Nhóm ngành
          <select value={sector} onChange={(event) => updateFilter(setSector, event.target.value)}>
            <option value="">Tất cả ngành</option>
            {(result?.available_sectors ?? []).map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Trạng thái
          <select value={listingStatus} onChange={(event) => updateFilter(setListingStatus, event.target.value)}>
            <option value="">Tất cả trạng thái</option>
            {(result?.available_listing_statuses ?? ["active"]).map((item) => (
              <option key={item} value={item}>{statusLabels[item] ?? item}</option>
            ))}
          </select>
        </label>
        <label>
          Số dòng
          <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
            {[5, 10, 20, 50].map((value) => <option key={value} value={value}>{value} dòng</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div className="explorer-message is-error" role="alert">
          <div><strong>Không tải được danh mục.</strong><span>{error}</span></div>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>Thử lại</button>
        </div>
      )}

      <div className="securities-table-wrap" aria-busy={loading}>
        <table className="securities-table">
          <thead>
            <tr>
              <th scope="col"><span className="sr-only">Watchlist</span></th>
              <th scope="col" aria-sort={sortBy === "symbol" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>{sortButton("Mã", "symbol")}</th>
              <th scope="col" aria-sort={sortBy === "name" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>{sortButton("Doanh nghiệp", "name")}</th>
              <th scope="col">Sàn</th>
              <th scope="col">Nhóm ngành</th>
              <th scope="col" aria-sort={sortBy === "price" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>{sortButton("Giá", "price", "Giá đóng cửa gần nhất được lưu")}</th>
              <th scope="col" aria-sort={sortBy === "change" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>{sortButton("Thay đổi", "change", "Thay đổi so với quan sát liền trước")}</th>
              <th scope="col" aria-sort={sortBy === "volume" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>{sortButton("Khối lượng", "volume")}</th>
              <th scope="col"><abbr title="Giá đóng cửa nhân khối lượng; chỉ là giá trị ước tính từ dữ liệu lưu">GTGD</abbr></th>
              <th scope="col"><abbr title="Hệ số giá trên lợi nhuận từ kỳ BCTC mới nhất nếu có">P/E</abbr></th>
              <th scope="col"><abbr title="Hệ số giá trên giá trị sổ sách từ kỳ BCTC mới nhất nếu có">P/B</abbr></th>
              <th scope="col">Cập nhật giá</th>
              <th scope="col"><span className="sr-only">Thao tác</span></th>
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: Math.min(pageSize, 5) }, (_, index) => (
              <tr className="loading-row" key={index}><td colSpan={13}><span /></td></tr>
            ))}
            {!loading && !error && items.map((item) => (
              <SecurityRow
                key={item.symbol}
                item={item}
                pinned={pinned.includes(item.symbol)}
                active={activeSymbol === item.symbol}
                onPin={() => togglePinned(item.symbol)}
                onAnalyze={() => onAnalyze(item.symbol)}
              />
            ))}
            {!loading && !error && items.length === 0 && (
              <tr className="empty-row"><td colSpan={13}><strong>Không có mã phù hợp.</strong><span>Hãy bỏ bớt bộ lọc hoặc thử tên doanh nghiệp không dấu.</span></td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="explorer-pagination">
        <p>
          {result?.total
            ? `Trang ${result.page}/${result.total_pages} · ${integer.format(result.total)} mã từ securities master`
            : "Danh mục phản ánh đúng registry hiện có."}
        </p>
        <div>
          <button type="button" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>Trang trước</button>
          <button type="button" disabled={loading || !result || page >= result.total_pages} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
        </div>
      </div>
      <p className="explorer-provenance">
        Danh mục bootstrap có 13 mã và có thể mở rộng bằng CSV/XLSX được phép qua API quản trị.
        Giá, định giá và timestamp chỉ hiển thị khi database có bản ghi tương ứng.
      </p>
    </section>
  );
}

function SecurityRow({
  item,
  pinned,
  active,
  onPin,
  onAnalyze,
}: {
  item: SecuritiesExplorerItem;
  pinned: boolean;
  active: boolean;
  onPin: () => void;
  onAnalyze: () => void;
}) {
  const changeClass = item.change_percent === null ? "" : item.change_percent >= 0 ? "positive" : "negative";
  const updatedAt = formatDate(item.price_updated_at);
  return (
    <tr className={active ? "is-active" : undefined}>
      <td data-label="Watchlist">
        <button
          type="button"
          className={pinned ? "pin-button is-pinned" : "pin-button"}
          onClick={onPin}
          aria-label={`${pinned ? "Bỏ ghim" : "Thêm"} ${item.symbol} ${pinned ? "khỏi" : "vào"} watchlist cục bộ`}
          title={pinned ? "Bỏ khỏi watchlist cục bộ" : "Thêm vào watchlist cục bộ"}
        >
          <PinIcon active={pinned} />
        </button>
      </td>
      <td data-label="Mã"><button type="button" className="symbol-button" onClick={onAnalyze}>{item.symbol}</button></td>
      <td data-label="Doanh nghiệp"><strong className="company-name">{item.name}</strong><small>{statusLabels[item.listing_status] ?? item.listing_status}</small></td>
      <td data-label="Sàn"><span className="exchange-tag">{item.exchange === "UPCOM" ? "UPCoM" : item.exchange}</span></td>
      <td data-label="Nhóm ngành"><span>{item.sector ?? "Chưa phân loại"}</span>{item.industry && <small>{item.industry}</small>}</td>
      <td data-label="Giá" className="numeric">{item.latest_price === null ? <MissingValue /> : <><strong>{integer.format(item.latest_price)}</strong><small>{item.currency}</small></>}</td>
      <td data-label="Thay đổi" className={`numeric ${changeClass}`}>{item.change_percent === null ? <MissingValue /> : `${item.change_percent >= 0 ? "+" : ""}${decimal.format(item.change_percent)}%`}</td>
      <td data-label="Khối lượng" className="numeric">{item.volume === null ? <MissingValue /> : integer.format(item.volume)}</td>
      <td data-label="GTGD" className="numeric">{item.trading_value === null ? <MissingValue /> : formatTradingValue(item.trading_value)}</td>
      <td data-label="P/E" className="numeric">{item.pe === null ? <MissingValue /> : decimal.format(item.pe)}</td>
      <td data-label="P/B" className="numeric">{item.pb === null ? <MissingValue /> : decimal.format(item.pb)}</td>
      <td data-label="Cập nhật giá">
        <span>{updatedAt ?? <MissingValue />}</span>
        {item.price_source && (
          <small>
            {item.price_source}
            {item.price_trust_status === "fixture" ? " · fixture" : ""}
            {item.price_trust_status === "development_only" ? " · nguồn phát triển" : ""}
            {item.price_is_stale ? " · dữ liệu cũ" : ""}
          </small>
        )}
      </td>
      <td data-label="Thao tác"><button type="button" className="analyze-button" onClick={onAnalyze}>Xem phân tích</button></td>
    </tr>
  );
}
