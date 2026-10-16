"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";
type Payload = Record<string, unknown>;

export function AdminDataOperations() {
  const [token, setToken] = useState("");
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function call(path: string, method = "GET") {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}${path}`, {
        method,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        cache: "no-store",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `API trả mã ${response.status}`);
      setPayload(body as Payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tải dữ liệu vận hành.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="query-strip" style={{ maxWidth: 1100, margin: "0 auto" }}>
      <p className="eyebrow">Data operations</p>
      <h1>Giám sát dữ liệu</h1>
      <p className="explorer-provenance">
        Token chỉ tồn tại trong bộ nhớ của trang này, không được lưu localStorage hay đóng gói vào frontend.
      </p>
      <label>
        Admin token
        <input value={token} onChange={(event) => setToken(event.target.value)} type="password" autoComplete="off" />
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="button" onClick={() => call("/admin/operations")} disabled={loading}>Tải coverage & jobs</button>
        <button type="button" onClick={() => call("/data-platform/capabilities")} disabled={loading}>Tải capability & nguồn</button>
        <button type="button" onClick={() => call("/data-quality/reconciliation")} disabled={loading}>Tải đối chiếu dữ liệu</button>
        <button type="button" onClick={() => call("/admin/scheduler/run-once", "POST")} disabled={loading}>Chạy scheduler một vòng</button>
        <button type="button" onClick={() => call("/admin/providers/health-check", "POST")} disabled={loading}>Kiểm tra provider</button>
      </div>
      {error && <p className="explorer-message is-error">{error}</p>}
      {Array.isArray(payload?.capabilities) && (
        <div style={{ overflowX: "auto", marginTop: 16 }}>
          <table>
            <thead><tr><th>Capability</th><th>Trạng thái</th><th>Provider</th><th>Bản ghi</th><th>Blocker</th></tr></thead>
            <tbody>{(payload.capabilities as Array<Record<string, unknown>>).map((item) => (
              <tr key={String(item.capability)}>
                <td>{String(item.capability)}</td>
                <td>{String(item.status)}</td>
                <td>{String(item.provider ?? "Chưa có")}</td>
                <td>{String(item.records ?? 0)}</td>
                <td>{String(item.blocker ?? "—")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {payload && <pre style={{ overflow: "auto", background: "var(--color-paper-muted)", padding: 16 }}>{JSON.stringify(payload, null, 2)}</pre>}
    </main>
  );
}
