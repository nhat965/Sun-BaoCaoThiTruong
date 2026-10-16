# Vnstock full-market backfill acceptance

Ngày kiểm tra: 2026-10-15. Đây là báo cáo dữ liệu thực tế trong môi trường
local, không phải cam kết realtime hoặc quyền phân phối dữ liệu thương mại.

## Trạng thái nguồn

- Vnstock `5.0.1` đã đăng ký thành công bằng credential store cục bộ; key
  không nằm trong source code, log hoặc checkpoint.
- Tài khoản được Vnstock xác định là **Community**. Khi gọi Finance, SDK cảnh
  báo Community chỉ trả **8 kỳ báo cáo gần nhất**; quota đầy đủ hơn yêu cầu
  tier khác. Không bypass giới hạn này.
- Usage endpoint sau nghiệm thu báo giới hạn 60 request/phút, 3.600/giờ,
  10.000/ngày và 100.000/tháng; mức đã dùng là 131 request trong ngày/giờ,
  18 request trong phút hiện tại, không có 429/403 quan sát được. Vnstock báo
  6 request đang chờ ghi nhận.
- Kiểm tra lại CLI sau audit (`vnstock status`, `vnstock --json usage`) hiện
  trả **Guest / unauthenticated** (20/phút, 1.200/giờ, 5.000/ngày). Vì vậy
  không chạy thêm backfill và không coi provider hiện tại là LIVE cho request
  mới. Các batch bên dưới chỉ là bằng chứng lịch sử của lần credential Community
  đã xác thực; cần đăng ký lại credential trong credential store trước khi mở
  batch tiếp theo.
- Community mở route `market.equity.ohlcv`, `market.index.ohlcv`,
  `reference.equity.list` và `fundamental.equity.*`; lịch sử daily tối đa SDK
  công bố là 2.920 ngày.
- OHLCV dùng API chính thức của Vnstock v5, route `vci`, giá equity được
  chuẩn hóa từ nghìn VND sang VND theo tài liệu SDK và gắn provenance
  `Vnstock v5 (vci)`, `source_mode=live`, `freshness=daily/delayed`.
- Vnstock là client library; điều khoản upstream và quyền tái phân phối vẫn
  phải được operator xác minh riêng.

## Backfill đã nghiệm thu

Tiến trình `apps/api/scripts/vnstock_backfill.py` có:

- provider cố định `vnstock`, không fallback sang Yahoo/fixture;
- checkpoint/resume ở `.runtime/vnstock_backfill_checkpoint.json`;
- retry exponential backoff, pause giữa request, và dừng khi nhận diện
  rate-limit/quota/403/permission;
- explicit initial/incremental mode và upsert idempotent qua
  `DataSyncService`;
- incremental Vnstock reads dùng cửa sổ reconciliation tối đa 60 phiên vì API
  daily công khai nhận `length` thay vì cursor; cursor persisted quyết định
  những phiên nào được ghi.
- không ghi credential vào checkpoint.

Các batch live đã chạy:

| Batch | Thành công | Resume/bỏ qua | Lỗi | Thời gian |
|---|---:|---:|---:|---:|
| 5 mã | 5 | 0 | 0 | 7,87 giây |
| 20 mã | 15 mới | 5 | 0 | 22,22 giây |
| replay 20 mã | 20 | 0 | 0 | 27,39 giây |
| 50 mã | 30 mới | 20 | 0 | 42,72 giây |

Replay 20 mã không tạo duplicate. Kiểm tra group theo
`security_id + market_session_date + interval + adjusted + provider_id` trả
`duplicate_groups=0`.

## Coverage sau batch 50

Chạy `python apps/api/scripts/vnstock_coverage.py` trên SQLite local:

- Securities active: **1.520**
- Mã có OHLCV Vnstock: **52** (bao gồm SSI đã có trong database trước snapshot)
- Mã chưa có OHLCV: **1.468**
- OHLCV records: **21.670**
- Mã đạt ít nhất 20 phiên: **51**
- Mã đạt ít nhất 50 phiên: **51**
- Mã đạt ít nhất 200 phiên: **46**
- Nguồn: **100% live**, adjusted: **100% true**
- OHLC không hợp lệ: **0**
- Volume âm: **0**
- Duplicate groups: **0**
- Zero-volume observations: **864** (cờ chất lượng, không tự sửa)
- Calendar gaps > 4 ngày: **789** (chỉ cảnh báo vì chưa có lịch giao dịch
  chính thức để phân biệt cuối tuần/ngày lễ)

Các số liệu trên là coverage đã lưu, không suy ra rằng 1.520 mã đều có giá
hoặc rằng dữ liệu là realtime.

## Khảo sát BCTC Vnstock (không ghi canonical database)

SDK `Finance` v5 có các surface:

- `income_statement()`
- `balance_sheet()`
- `cash_flow()`
- `history()` và `ratio()`

Đã gọi thử HPG, FPT và SHB với nguồn VCI và KBS, kỳ `quarter` trong lần probe
trước:

- Cả ba mã đều trả income statement, balance sheet và cash flow.
- Schema quan sát được là dạng dòng: `period`, `id`, `name`, `order`, `level`,
  `unit`, `value`; balance sheet thêm `off_balance`.
- `period` có dạng `2026-Q2`; `unit` trả `VNĐ`.
- Một số giá trị KBS trả `NaN`; không được đưa thẳng vào canonical engine.
- Community giới hạn 8 kỳ gần nhất; không có đủ căn cứ để coi đây là full
  historical financial statements.

Do chưa có adapter mapping/validation cho từng `id`, đơn vị, consolidated vs
separate và semantics dòng tiền, các response này **chỉ là discovery/blocked**;
chưa persist vào `financial_periods` hoặc `financial_statement_items`.

Lần probe lại HPG/FPT/SHB/SSI theo quý và năm bị `NetworkError` khi SDK không
lấy được client policy từ `vnstocks.com`; không dùng lỗi này để thay thế bằng
dữ liệu khác. Bản ghi raw nằm ở `.runtime/vnstock_financial_discovery_all.json`.

## PostgreSQL acceptance

Chưa thể đánh dấu PASS. Máy nghiệm thu hiện không có Docker, `psql` hoặc
`pg_isready`; các batch trên chạy SQLite local. `docker-compose.yml` vẫn có
PostgreSQL 16 và script `apps/api/scripts/verify_postgres_acceptance.py` sẽ
trả BLOCKED nếu không có `DATABASE_URL` PostgreSQL. Cần chạy các bước sau trên
môi trường có PostgreSQL 16 trước khi tuyên bố production acceptance:

1. `docker compose up -d db`
2. Chạy Alembic migrations với `DATABASE_URL=postgresql+psycopg://...`
3. Import securities master và chạy batch 5/20 trên PostgreSQL.
4. Chạy replay/concurrent jobs và kiểm tra duplicate/lease.
5. Đo latency, RAM và query count.

## Cách tiếp tục mở rộng

```powershell
$env:PYTHONPATH = "apps/api"
python apps/api/scripts/vnstock_backfill.py --max-symbols 100 --batch-size 5
python apps/api/scripts/vnstock_coverage.py
```

Chỉ tăng `--max-symbols` sau khi kiểm tra checkpoint, quota và lỗi provider.
Không chạy `--all` trong môi trường Community nếu chưa có giới hạn/nghiệm thu
quyền sử dụng phù hợp.

Nguồn tham khảo: [Vnstock Market API](https://www.vnstocks.com/docs/vnstock/thi-truong-market),
[Vnstock Reference API](https://www.vnstocks.com/docs/vnstock/tham-chieu-reference),
[Vnstock Fundamental API](https://www.vnstocks.com/docs/vnstock/co-ban-fundamental).
