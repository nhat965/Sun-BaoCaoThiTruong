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

## Phân tích HPG và tạo báo cáo

```bash
curl http://localhost:8000/api/v1/stocks/HPG/analysis
curl -X POST http://localhost:8000/api/v1/stocks/HPG/reports --output HPG-report.pdf
```

Tìm kiếm không dấu và nhập danh mục chứng khoán từ nguồn được phép:

```bash
curl "http://localhost:8000/api/v1/stocks/search?q=hoa%20phat"
curl -X POST http://localhost:8000/api/v1/securities/import \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: text/csv" -H "X-Source-Name: authorized-export" \
  --data-binary @securities.csv
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
- Pipeline BCTC và công thức nền tảng đã có cho CSV được cấp phép; chưa có credential provider tài chính live, peer set, dải lịch sử hoặc DCF.
- Chưa điều chỉnh đầy đủ corporate actions, lịch nghỉ giao dịch, dữ liệu intraday, sentiment mạng xã hội hay danh mục VPS.
- Tin tức được khớp theo tiêu đề/từ khóa nên có thể bỏ sót bài liên quan.
- Jobs EOD, watchlist và alert-rule đã có persistence/idempotency; cần worker/scheduler production để chạy định kỳ.
- PDF dùng font hệ thống và có thể bỏ dấu khi môi trường thiếu font Unicode tương thích.

Xem [implementation status](docs/IMPLEMENTATION_STATUS.md), [test report](docs/testing/TEST_REPORT.md), [architecture](docs/architecture/ARCHITECTURE.md), và [data sources](docs/integrations/DATA_SOURCES.md).

