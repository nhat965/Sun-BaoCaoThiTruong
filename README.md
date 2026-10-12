# Mạch Thị Trường — AI Market Intelligence V3

Ứng dụng nghiên cứu cổ phiếu Việt Nam với luồng hoàn chỉnh: tìm theo mã/tên → lấy và kiểm định OHLCV có nguồn → tính chỉ báo kỹ thuật → hiển thị biểu đồ → tổng hợp metadata tin liên quan → xuất báo cáo PDF.

## Trạng thái tích hợp

| Nguồn | Trạng thái | Ghi chú |
|---|---|---|
| Yahoo Finance chart API | Live, không chính thức | Không cần khóa; khả dụng phụ thuộc điều khoản/độ ổn định upstream. Mã HOSE dùng hậu tố `.VN`. |
| Configurable RSS feeds | Live metadata | Chỉ dùng metadata, URL và tiêu đề; không sao chép toàn văn. Mặc định VnExpress, nguồn khác cấu hình qua `NEWS_FEEDS`. |
| FireAnt | Theo dõi trạng thái; bị chặn khi thiếu token | Chỉ gọi `/monitoring/status` khi có token. Chưa tuyên bố dữ liệu nào là live khi chưa xác minh scope/entitlement. |
| VPS SmartOne | Không kết nối | Không dùng API không được hỗ trợ; MVP không giao dịch. |
| LLM | Tùy chọn | `POST /api/v1/analyst/chat` dùng tool outputs có evidence; thiếu cấu hình sẽ fallback xác định, không đoán số. |

## Chạy bằng Docker Compose

Yêu cầu Docker Desktop và Docker Compose:

```bash
docker compose up --build
```

Mở `http://localhost:3000`. API docs ở `http://localhost:8000/docs`.

## Chạy cục bộ

Backend (Python 3.12+):

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate
pip install -e .[dev]
python scripts/adopt_legacy_database.py
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend (Node 20+):

```bash
cd apps/web
npm install
npm run dev
```

Sao chép `.env.example` thành `.env`. Mặc định local dùng SQLite; Compose dùng PostgreSQL. Lệnh `adopt_legacy_database.py` chỉ cần cho database MVP cũ chưa có version; nó kiểm tra cấu trúc trước khi stamp và không xóa dữ liệu.

`MAX_REQUEST_BYTES` giới hạn số byte thực tế mà API chấp nhận, kể cả request
stream/chunked không có `Content-Length`. Khi triển khai sau reverse proxy, đặt giới hạn
proxy bằng hoặc thấp hơn giá trị này (ví dụ Nginx `client_max_body_size 5m;`) và tắt
request buffering chỉ khi hạ tầng đã được kiểm thử với giới hạn tương đương.

## Phân tích HPG và tạo báo cáo

```bash
curl http://localhost:8000/api/v1/stocks/HPG/analysis
curl "http://localhost:8000/api/v1/stocks/HPG/fundamentals/history?period_type=year&statement_scope=consolidated"
curl "http://localhost:8000/api/v1/stocks/HPG/news?event_category=earnings&limit=20"
curl -X POST http://localhost:8000/api/v1/stocks/HPG/reports --output HPG-report.pdf
curl http://localhost:8000/api/v1/data-quality
```

Tìm kiếm không dấu và nhập danh mục chứng khoán từ nguồn được phép:

```bash
curl "http://localhost:8000/api/v1/stocks/search?q=hoa%20phat"
curl -X POST http://localhost:8000/api/v1/securities/import \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: text/csv" -H "X-Source-Name: authorized-export" \
  --data-binary @securities.csv
# XLSX dùng cùng các cột bắt buộc symbol, name, exchange:
curl -X POST http://localhost:8000/api/v1/securities/import/xlsx \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  -H "X-Source-Name: authorized-workbook" --data-binary @securities.xlsx
```

Corporate actions chỉ được lưu từ file được ủy quyền; hệ thống không tự suy đoán điều
chỉnh giá. CSV dùng `action_type,effective_at,ratio,cash_amount,verification_status,source_url`:

```bash
curl -X POST http://localhost:8000/api/v1/stocks/HPG/corporate-actions/import \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" -H "Content-Type: text/csv" \
  -H "X-Source-Name: authorized-actions-export" --data-binary @corporate-actions.csv
curl http://localhost:8000/api/v1/stocks/HPG/corporate-actions
```

Nhập BCTC theo schema CSV đã kiểm tra:

```bash
curl -X POST http://localhost:8000/api/v1/stocks/HPG/financials/import \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: text/csv" -H "X-Source-Name: authorized-financial-export" \
  --data-binary @financial-statements.csv
curl http://localhost:8000/api/v1/stocks/HPG/fundamentals
curl -X POST http://localhost:8000/api/v1/analyst/chat -H "Content-Type: application/json" \
  -d '{"symbol":"HPG","question":"Tóm tắt rủi ro và dữ liệu cần theo dõi"}'
# Public valuation calculation does not persist. Persisting a scenario requires admin auth:
curl -X POST http://localhost:8000/api/v1/fundamentals/valuation/persist \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"symbol":"HPG","eps":2,"bvps":10,"pe_multiple":10,"pb_multiple":2}'
# DCF công khai chỉ tính toán, không lưu; mọi dự báo đều do người dùng cung cấp:
curl -X POST http://localhost:8000/api/v1/fundamentals/valuation/dcf \
  -H "Content-Type: application/json" \
  -d '{"symbol":"HPG","forecast_free_cash_flows":[100,110],"discount_rate":0.1,"terminal_growth_rate":0.03,"net_debt":50,"shares_outstanding":10}'
```

Nếu upstream không truy cập được, API trả lỗi `503` có cấu trúc và giao diện hiển thị trạng thái thiếu dữ liệu. Chỉ bật `MARKET_DATA_MODE=fixture` cho demo/test; dữ liệu sẽ được dán nhãn `fixture` rõ ràng.

## Kiểm thử

```bash
cd apps/api && pytest
cd apps/web && npm run lint && npm run build
```

## Giới hạn hiện tại

- Yahoo Finance không phải nguồn dữ liệu được cấp phép riêng cho sản phẩm này; cần thay bằng feed có hợp đồng trước khi phân phối thương mại.
- Registry kèm theo chỉ là bootstrap 13 mã, được ghi nguồn rõ ràng; độ phủ đầy đủ cần file CSV được phép hoặc connector master-data có hợp đồng.
- Trang chất lượng dữ liệu hiển thị độ phủ registry, số quan sát giá, mốc thị trường, lịch sử thành công/thất bại của connector và các nguồn mới chỉ cấu hình/chưa xác minh.
- Pipeline BCTC và công thức nền tảng đã có cho CSV được cấp phép; chưa có credential provider tài chính live, peer set, dải lịch sử hoặc DCF.
- Chưa điều chỉnh đầy đủ corporate actions, lịch nghỉ giao dịch, dữ liệu intraday, sentiment mạng xã hội hay danh mục VPS.
- Tin tức được khớp theo tiêu đề/từ khóa nên có thể bỏ sót bài liên quan.
- Jobs EOD, watchlist và alert-rule đã có persistence/idempotency; cần worker/scheduler production để chạy định kỳ.
- PDF dùng font hệ thống và có thể bỏ dấu khi môi trường thiếu font Unicode tương thích.

Xem [implementation status](docs/IMPLEMENTATION_STATUS.md), [test report](docs/testing/TEST_REPORT.md), [architecture](docs/architecture/ARCHITECTURE.md), và [data sources](docs/integrations/DATA_SOURCES.md).

