# Mạch Thị Trường — AI Market Intelligence V4.1

Ứng dụng nghiên cứu cổ phiếu Việt Nam với luồng hoàn chỉnh: tìm theo mã/tên → lấy và kiểm định OHLCV có nguồn → tính chỉ báo kỹ thuật → hiển thị biểu đồ → tổng hợp metadata tin liên quan → xuất báo cáo PDF.

## Trạng thái tích hợp

| Nguồn | Trạng thái | Ghi chú |
|---|---|---|
| Yahoo Finance chart API | Development connector, delayed | Không cần khóa; có thể truy xuất OHLCV khi upstream đáp ứng, nhưng chưa xác minh quyền phân phối thương mại và không phải realtime production. Mã HOSE dùng hậu tố `.VN`. |
| Vnstock v5 | Live verified, delayed, Community-limited | Đã kiểm thử route `vci`, danh mục 1.520 mã và backfill OHLCV theo batch; chưa phải realtime/full-market và quyền upstream phải được xác minh. Xem [`docs/integrations/VNSTOCK.md`](docs/integrations/VNSTOCK.md) và [`docs/data/VNSTOCK_FULL_MARKET_BACKFILL.md`](docs/data/VNSTOCK_FULL_MARKET_BACKFILL.md). |
| Configurable RSS feeds | Configured metadata, unverified | Chỉ dùng metadata, URL và tiêu đề; không sao chép toàn văn. Mặc định VnExpress, nguồn khác cấu hình qua `NEWS_FEEDS`; chưa tính là live nếu chưa có lần truy xuất thành công được ghi nhận. |
| FireAnt | Theo dõi trạng thái; bị chặn khi thiếu token | Chỉ gọi `/monitoring/status` khi có token. Chưa tuyên bố dữ liệu nào là live khi chưa xác minh scope/entitlement. |
| SSI FastConnect | BLOCKED | Tài liệu chính thức đã khảo sát; cần tài khoản, API key/secret và lần kiểm thử được cấp quyền. |
| FiinGroup Datafeed | BLOCKED | Có phạm vi market/company/BCTC phù hợp; cần hợp đồng, credential và quyền phân phối. |
| File được người dùng cấp quyền | Sẵn sàng | Nhập securities CSV/XLSX, corporate actions CSV và BCTC CSV có provenance. |
| VPS SmartOne | Không kết nối | Không dùng API không được hỗ trợ; MVP không giao dịch. |
| LLM | Tùy chọn | `POST /api/v1/analyst/chat` dùng tool outputs có evidence; thiếu cấu hình sẽ fallback xác định, không đoán số. |

## Chạy bằng Docker Compose

Yêu cầu Docker Desktop và Docker Compose:

```bash
docker compose up --build
```

Mở `http://localhost:3000`. API docs ở `http://localhost:8000/docs`.

Worker scheduler chạy tách khỏi FastAPI. Mặc định worker bị tắt để tránh chạy nhầm trong
môi trường phát triển; bật bằng `SCHEDULER_ENABLED=true` sau khi cấu hình nguồn được cấp
quyền. Chạy kiểm tra một vòng có chủ đích bằng `cd apps/api && python scripts/run_scheduler.py --once`.
Coverage database có tại `GET /api/v1/data-quality/coverage`; trang vận hành quản trị là
`/admin` và chỉ giữ admin token trong bộ nhớ phiên, không lưu vào localStorage. Acceptance
release và PostgreSQL lease checks được mô tả trong
[`docs/release/RELEASE_ACCEPTANCE.md`](docs/release/RELEASE_ACCEPTANCE.md) và
[`docs/release/DEPLOYMENT_RUNBOOK.md`](docs/release/DEPLOYMENT_RUNBOOK.md).
Ma trận capability/provenance của Task 05 có tại `GET /api/v1/data-platform/capabilities`
và [`docs/data/TASK05_DATA_PLATFORM_AUDIT.md`](docs/data/TASK05_DATA_PLATFORM_AUDIT.md).
Đối chiếu nội bộ có tại `GET /api/v1/data-quality/reconciliation` hoặc lệnh
`python scripts/data_reconciliation_report.py` trong `apps/api`.
Endpoint này chỉ đọc database; `IMPLEMENTED_AND_LIVE_VERIFIED` chỉ xuất hiện sau khi một
request được cấp quyền thành công và sync run được lưu lại.

Backfill Vnstock có checkpoint/resume và dừng an toàn khi gặp quota hoặc quyền bị từ chối:
`python apps/api/scripts/vnstock_backfill.py --max-symbols 5`. Báo cáo coverage không gọi
provider và chạy bằng `python apps/api/scripts/vnstock_coverage.py`. Batch 5/20/50 đã được
nghiệm thu live; dữ liệu BCTC Vnstock mới chỉ ở bước discovery, chưa ghi canonical engine.

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
curl http://localhost:8000/api/v1/market/overview
```

Tìm kiếm không dấu và nhập danh mục chứng khoán từ nguồn được phép:

```bash
curl "http://localhost:8000/api/v1/stocks/search?q=hoa%20phat"
curl "http://localhost:8000/api/v1/securities?q=hoa%20phat&exchange=HOSE&sort_by=volume&sort_order=desc&page=1&page_size=20"
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

`GET /api/v1/securities` lọc, sắp xếp và phân trang trực tiếp trong cơ sở dữ liệu;
response trả facets sàn/ngành/trạng thái cùng timestamp tạo kết quả. Trang Danh mục dùng
API này và chỉ hiển thị giá, biến động, khối lượng, giá trị giao dịch, P/E hoặc P/B khi
có bản ghi nguồn tương ứng. Nút ghim dùng watchlist cục bộ trong trình duyệt vì các
watchlist dùng chung ở server là route ghi được bảo vệ bằng quyền admin.

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
curl http://localhost:8000/api/v1/stocks/HPG/financial-statements
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
# Ma trận nhạy cảm cũng chỉ dùng giả định do người dùng cung cấp:
curl -X POST http://localhost:8000/api/v1/fundamentals/valuation/dcf/sensitivity \
  -H "Content-Type: application/json" \
  -d '{"symbol":"HPG","forecast_free_cash_flows":[100,110],"discount_rates":[0.09,0.1,0.11],"terminal_growth_rates":[0.02,0.03,0.04],"net_debt":50,"shares_outstanding":10}'
```

CSV BCTC cần các cột `period_end,period_type,fiscal_year,statement_type,item_code,value,unit`.
Các cột nên có là `fiscal_quarter,reported_at,statement_scope,statement_status,currency,verification_status,source_url`.
`period_type` nhận `quarter|year|ttm`; `statement_type` nhận `income|balance|cash_flow`;
`statement_scope` nhận `consolidated|separate`. Đơn vị tiền hỗ trợ `VND`, `THOUSAND_VND`,
`MILLION_VND`, `BILLION_VND` và được chuẩn hóa về VND trong khi vẫn giữ `raw_value/raw_unit`.
Đơn vị `SHARES` và `RATIO` không đổi. Các `item_code` chính gồm `revenue`, `gross_profit`,
`net_income`, `total_assets`, `total_equity`, `total_liabilities`, `operating_cash_flow`,
`investing_cash_flow`, `financing_cash_flow`. Giá trị `verified` không bị bản
`unverified` ghi đè.

Đồng bộ giá có trạng thái, cursor và chống trùng lặp:

```bash
curl http://localhost:8000/api/v1/providers
curl -X POST "http://localhost:8000/api/v1/sync/prices/HPG?provider=yahoo" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
## Khi đã được SSI cấp quyền và cài official ssi-fc-data SDK:
curl -X POST "http://localhost:8000/api/v1/sync/securities?provider=ssi_fastconnect&markets=HOSE,HNX,UPCOM" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl -X POST "http://localhost:8000/api/v1/sync/prices/HPG?provider=ssi_fastconnect&mode=initial&limit=520" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl -X POST "http://localhost:8000/api/v1/sync/prices/HPG?provider=ssi_fastconnect&mode=incremental" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl -X POST "http://localhost:8000/api/v1/sync/indices?provider=ssi_fastconnect" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl -X POST http://localhost:8000/api/v1/sync/financials/HPG \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl http://localhost:8000/api/v1/sync/runs -H "Authorization: Bearer $ADMIN_API_TOKEN"
```

SSI FastConnect dùng SDK Python chính thức và chỉ được đánh dấu live sau khi có
credential, entitlement và một request thực tế thành công. Xem
`docs/integrations/SSI_OFFICIAL_SDK.md`; CSV/XLSX được cấp quyền vẫn hoạt động
độc lập khi SSI chưa được bật.

`sync/financials` trả `BLOCKED` cho đến khi một provider BCTC có credential, entitlement
và lần gọi thật thành công; dữ liệu file không bị mô tả nhầm là đồng bộ tự động.

Tạo snapshot thị trường và quản lý danh mục thủ công (các route ghi cần admin token):

```bash
curl -X POST http://localhost:8000/api/v1/market/reports/post_market \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
curl http://localhost:8000/api/v1/market/reports
curl -X POST http://localhost:8000/api/v1/portfolios \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Danh mục dài hạn","base_currency":"VND"}'
curl -X POST http://localhost:8000/api/v1/social/analyze \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"symbol":"HPG","content":"HPG có thể tăng trưởng nhưng đây chỉ là dự báo","source_name":"authorized-input"}]}'
```

Danh mục là sổ giao dịch thủ công/CSV, không kết nối đặt lệnh. Phân loại social chỉ
xử lý nội dung được người vận hành cung cấp hợp pháp và luôn trả uncertainty/limitations.

Nếu upstream không truy cập được, API trả lỗi `503` có cấu trúc và giao diện hiển thị trạng thái thiếu dữ liệu. Chỉ bật `MARKET_DATA_MODE=fixture` cho demo/test; dữ liệu sẽ được dán nhãn `fixture` rõ ràng.

## Kiểm thử

```bash
cd apps/api && pytest
cd apps/api && python scripts/benchmark_market_analytics.py
cd apps/api && python scripts/benchmark_market_analytics_postgres.py --database-url "$BENCHMARK_DATABASE_URL"
cd apps/web && npm run lint && npm run build
```

GitHub Actions lặp lại các bước này, chạy toàn bộ migration lên/xuống/lên trên
PostgreSQL 16 và chặn dependency production có lỗ hổng mức `high` trở lên.

## Giới hạn hiện tại

- Yahoo Finance không phải nguồn dữ liệu được cấp phép riêng cho sản phẩm này; cần thay bằng feed có hợp đồng trước khi phân phối thương mại.
- Registry kèm theo chỉ là bootstrap 13 mã, được ghi nguồn rõ ràng; độ phủ đầy đủ cần file CSV được phép hoặc connector master-data có hợp đồng.
- Trang chất lượng dữ liệu hiển thị độ phủ theo market session/exchange, số mã có giá và actual trading value, mốc thị trường, freshness evidence, lịch sử thành công/thất bại của connector và các nguồn mới chỉ cấu hình/chưa xác minh.
- Pipeline BCTC, công thức nền tảng và DCF theo giả định người dùng đã có; chưa có credential provider tài chính live, peer set hoặc dải định giá lịch sử.
- Chưa điều chỉnh đầy đủ corporate actions, lịch nghỉ giao dịch, dữ liệu intraday, live social feed hay danh mục VPS.
- Tin tức được khớp theo tiêu đề/từ khóa nên có thể bỏ sót bài liên quan.
- Jobs EOD, watchlist, alert-rule và daily snapshot đã có lease/idempotency/retry; worker production đã có trong Compose nhưng chỉ tự động cập nhật capability/provider được cấp quyền.
- PDF dùng font hệ thống và có thể bỏ dấu khi môi trường thiếu font Unicode tương thích.

Xem [implementation status](docs/IMPLEMENTATION_STATUS.md), [test report](docs/testing/TEST_REPORT.md), [production-readiness audit](docs/testing/PRODUCTION_READINESS_AUDIT.md), [architecture](docs/architecture/ARCHITECTURE.md), và [data sources](docs/integrations/DATA_SOURCES.md).


## Đồng bộ BCTC tự động từ nguồn HTTPS CSV được cấp quyền

Nếu nhà cung cấp dữ liệu hoặc hệ thống nội bộ của bạn cho phép tự động truy xuất CSV BCTC,
cấu hình các biến môi trường sau **chỉ sau khi đã xác minh quyền sử dụng dữ liệu**:

```dotenv
FINANCIAL_CSV_URL_TEMPLATE=https://your-licensed-data-host.example/financials/{symbol}.csv
FINANCIAL_CSV_BEARER_TOKEN=replace-with-your-provider-token
FINANCIAL_CSV_RIGHTS_CONFIRMED=true
```

Endpoint `POST /api/v1/sync/financials/{symbol}` (yêu cầu admin bearer token)
sẽ lấy CSV bằng HTTPS, kiểm tra kích thước, chuẩn hóa qua cùng logic CSV hiện tại
và lưu trạng thái đồng bộ vào `/api/v1/sync/runs`.
Endpoint này được worker production gọi theo lịch khi feed đã được vận hành và cấp quyền;
job BCTC vẫn giữ trạng thái `BLOCKED` cho đến khi credential, entitlement và lần gọi thật
được xác minh.
Feed phải hỗ trợ CSV có các cột `period_end,period_type,fiscal_year,statement_type,item_code,value,unit`;
xem định dạng đầy đủ ở hướng dẫn nhập BCTC phía trên.
Không nhúng token vào URL; dùng `FINANCIAL_CSV_BEARER_TOKEN`.
Cơ chế này không phải tích hợp API native của FiinGroup hoặc FireAnt và không tự cấp
quyền phân phối dữ liệu. Khi chưa cấu hình quyền, API trả `BLOCKED` thay vì tự tạo dữ liệu.

