# Data coverage recovery audit — 2026-10-15

Đây là snapshot read-only trước khi chạy thêm batch. Báo cáo được tạo bằng
`apps/api/scripts/vnstock_coverage.py` trên SQLite local và không ghi lại giá.

## Coverage hiện tại

| Hạng mục | Kết quả | Phân loại |
|---|---:|---|
| Active securities | 1.520 | REAL VERIFIED — securities master local |
| HOSE / HNX / UPCoM | 406 / 299 / 815 | REAL VERIFIED |
| OHLCV có dữ liệu | 52 mã | REAL VERIFIED — Vnstock rows đã persist |
| OHLCV chưa có dữ liệu | 1.468 mã | NOT BACKFILLED / chưa có attempt |
| Provider `unsupported` đã xác nhận | 0 | Chưa có attempt/provider error tương ứng |
| Lỗi hoặc blocked đã ghi nhận | 0 | Không quan sát trong các batch đã chạy |
| OHLCV records | 21.670 | REAL VERIFIED, `source_mode=live` |
| Mã đạt ≥20 / ≥50 / ≥200 phiên | 51 / 51 / 46 | REAL VERIFIED |
| Duplicate groups | 0 | REAL VERIFIED |
| OHLC invalid / volume âm | 0 / 0 | REAL VERIFIED |
| Zero-volume observations | 864 | Cảnh báo chất lượng, không tự sửa |
| Financial periods | 0 mã | Không có BCTC production; acceptance fixture đã được dọn |

`SSI` có OHLCV rows trong database nhưng không có `DataSyncRun` tương ứng trong
snapshot này (dữ liệu đã tồn tại từ acceptance trước); không suy ra rằng SSI
đã được backfill bởi batch hiện tại. `SHB` chưa có financial period canonical.
Hai kỳ `acceptance-file` năm 2099 của HPG/FPT từng nằm trong SQLite do pytest
dùng chung database; chúng đã được xóa khỏi database vận hành và test đã có
cleanup tự động.

## Phân loại mã chưa có dữ liệu

- `not_backfilled`: 1.468 mã không có OHLCV và chưa có provider attempt trong
  `data_sync_runs`.
- `unsupported`: 0. Không gán nhãn unsupported chỉ vì chưa chạy mã đó.
- `failed_or_blocked`: 0 trong các attempt Vnstock đã ghi nhận.

Theo exchange/security type, registry hiện chỉ có `stock`: HOSE 406, HNX 299,
UPCoM 815. Đây là universe local đã nhập, không phải cam kết mọi mã đều được
Vnstock hỗ trợ.

## Chất lượng giá và lịch giao dịch

`apps/api/scripts/vnstock_quality_audit.py` phát hiện 3 cảnh báo thay đổi giá
từ 20% trở lên giữa các phiên liền kề có khoảng cách không quá bốn ngày. Tất
cả đang là `UNVERIFIED`; database không có corporate action đã xác minh gần các
cảnh báo và script không sửa giá. Các chênh lệch bắc qua khoảng trống dài bị
loại khỏi anomaly count cho tới khi có lịch sàn. Provider trả toàn bộ các bar
hiện có ở `adjusted=true` với chính sách `provider-adjusted`; phương pháp điều
chỉnh chưa được đối chiếu độc lập.

Có 789 khoảng cách lịch trên bốn ngày. Vì chưa cấu hình lịch HOSE/HNX/UPCoM
được cấp quyền, toàn bộ được giữ ở trạng thái `UNCONFIRMED`; số phiên thiếu đã
xác nhận là 0. Cuối tuần/ngày lễ không được coi là lỗi dữ liệu.

## Financial discovery

Lần probe trước đã quan sát được các surface `income_statement`,
`balance_sheet`, `cash_flow` cho HPG/FPT/SHB với VCI/KBS, schema dòng gồm
`period`, `id`, `name`, `order`, `level`, `unit`, `value` (balance sheet thêm
`off_balance`), và Community giới hạn 8 kỳ. Không ghi canonical vì chưa map
được semantics, đơn vị, consolidated/separate và original/amended.

Lần probe lại cả HPG/FPT/SHB/SSI (quý/năm, VCI/KBS) tại thời điểm audit bị
`NetworkError`: Vnstock không lấy được client policy hiện hành từ
`vnstocks.com`. Kết quả mới nhất vì vậy là **BLOCKED**, không được dùng để
tuyên bố BCTC live. Xem JSON raw tại `.runtime/vnstock_financial_discovery_all.json`.

## Bằng chứng và lệnh tái lập

```powershell
$env:PYTHONPATH = "apps/api"
.tools/python/python.exe apps/api/scripts/vnstock_coverage.py `
  --output .runtime/coverage_recovery_before.json
.tools/python/python.exe apps/api/scripts/vnstock_quality_audit.py `
  --output .runtime/vnstock_quality_audit.json
```

Các batch OHLCV trước đó là 5 mã, 20 mã, replay 20 mã và 50 mã; replay không
tạo duplicate. PostgreSQL acceptance vẫn **BLOCKED** vì môi trường không có
Docker/`psql` và `DATABASE_URL` PostgreSQL chưa được cấu hình. Không đánh dấu
full-market ingestion, realtime hay entitlement phân phối dữ liệu. Kiểm tra
`vnstock status` sau audit hiện trả Guest/unauthenticated; cần `vnstock register`
lại credential trước khi chạy batch mới. Không ghi credential vào source, log
hoặc checkpoint. Thử lại HPG ngày 2026-10-16 cũng trả `FAILED` từ connector,
không thêm row nào và coverage/duplicate count không thay đổi.
