# Data sources

## Khảo sát nguồn cho Task 02

| Tên nguồn | URL tài liệu | Dữ liệu hỗ trợ | Xác thực | Cấp quyền | Điều khoản sử dụng | Khả năng kết nối thực tế | Kết quả kiểm tra | Chi phí / giới hạn đã xác minh |
|---|---|---|---|---|---|---|---|---|
| Yahoo Finance chart | [Product API terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) | OHLCV ngày | Không có credential trong connector hiện tại | Không chứng minh quyền phân phối thương mại | Điều khoản Yahoo áp dụng; chỉ dùng connector phát triển | Đã triển khai, thay thế được | HPG và FPT gọi thật thành công ngày 2026-10-13; 120 dòng/mã, sync kế tiếp không tạo dòng trùng | Không có quota/quyền production được xác minh |
| Vnstock v5 | [Market API](https://www.vnstocks.com/docs/vnstock/thi-truong-market), [Reference](https://www.vnstocks.com/docs/vnstock-data/v5/tham-chieu-reference) | Securities metadata, OHLCV ngày, market indices qua upstream đã chọn | `vnstock register` và entitlement của upstream | Người vận hành phải xác minh quyền sử dụng/phân phối nguồn upstream | Vnstock là client, không phải nhà cung cấp dữ liệu | Adapter đã triển khai; chưa có request live được xác minh trong môi trường này | `BLOCKED/CONFIGURED` nếu package hoặc registration chưa sẵn sàng; không suy đoán endpoint | Phụ thuộc nguồn upstream; quota/chi phí không được giả định |
| FireAnt REST API v1 | [OpenAPI chính thức](https://api.fireant.vn/) | Scope được tài liệu hóa cho symbols, companies, finance và nội dung khác | OAuth2 Bearer với scope | Tài khoản, scope và entitlement | Cần thỏa thuận dữ liệu/quyền phân phối phù hợp | Capability được khai báo nhưng chưa bật | `BLOCKED`: không có token và chưa có lần gọi dữ liệu được cấp quyền | Giá/quota công khai chưa xác minh |
| SSI FastConnect API v3 | [Overview](https://developers.ssi.com.vn/docs/getting-started/overview), [registration](https://developers.ssi.com.vn/docs/getting-started/registration), [terms/environments](https://developers.ssi.com.vn/docs/getting-started/terms-and-environments) | Securities metadata, OHLCV ngày/intraday, market indices | API key + secret đổi Bearer JWT | Tài khoản SSI, đăng ký và được duyệt FastConnect | Điều khoản dịch vụ SSI và quyền phân phối áp dụng | Interface phù hợp nhưng connector chưa được bật | `BLOCKED`: không có key/secret, không đoán endpoint hoặc gọi ẩn | Rate-limit theo key/header; lịch sử ngày từ niêm yết, intraday một năm; giá dịch vụ chưa xác minh |
| FiinGroup API Datafeed | [Trang sản phẩm](https://datafeed.fiingroup.vn/), [API doanh nghiệp](https://datafeed.fiingroup.vn/api-doanh-nghiep) | Metadata, market data, sự kiện, BCTC hợp nhất/riêng và cash flow | Credential thương mại | Hợp đồng, entitlement, quyền phân phối | Theo hợp đồng dữ liệu FiinGroup | Schema/phạm vi phù hợp, chưa có credential | `BLOCKED`: không có quyền nên chưa gọi API thật | Liên hệ nhà cung cấp; giá công khai chưa xác minh |
| HNX/HOSE và công bố doanh nghiệp | [Danh sách niêm yết HNX](https://www.hnx.vn/co-phieu-etfs/chung-khoan-ny.html) | Danh sách/công bố và tài liệu doanh nghiệp | Duyệt công khai hoặc workflow tổ chức phát hành | Chưa xác minh bulk API và quyền tự động phân phối | Điều khoản từng sở/nguồn công bố áp dụng | Chỉ nhận làm provenance cho file hợp pháp | `BLOCKED` cho tự động hóa; không scrape/API nội bộ | Chưa xác minh |
| File do người dùng cấp quyền | Hướng dẫn import trong README | Securities CSV/XLSX, corporate actions CSV, BCTC CSV | Bearer admin của ứng dụng | Người vận hành xác nhận quyền sử dụng file | Quyền của nguồn gốc file vẫn áp dụng | Đã triển khai và kiểm thử | `AVAILABLE`: validate, normalize, upsert, audit sync | Không phí provider; giới hạn request/rate của ứng dụng |

## Yahoo Finance chart

Implemented as a replaceable, unauthenticated development connector. It resolves provider IDs from the securities registry, falling back to `.VN`, and records source URL, retrieval time, market time, freshness, currency, validation state and adjustment policy. It is not represented as a licensed commercial feed. Production must configure a contractual provider behind the same interface.

## VnExpress RSS

Implemented for public RSS metadata. The application stores/returns headline, publication timestamp, publisher and original URL only. Matching normalizes Vietnamese aliases, scores relevance, deduplicates titles and classifies a small deterministic event taxonomy. It is still keyword-based and may be incomplete.

## FireAnt

The official [FireAnt API documentation](https://api.fireant.vn/) advertises OAuth scopes including `companies-read`, `finance-read` and `posts-read`. The isolated connector can check the documented `/monitoring/status` endpoint when `FIREANT_ACCESS_TOKEN` is configured. Without a token it reports `unavailable` with a `BLOCKED` message and performs no request. A health response alone does not prove any data scope; market-data calls remain disabled until credentials, scopes, entitlements and redistribution rights are verified.

## SSI FastConnect and FiinGroup

Both sources are represented by capability metadata only. The application will not probe
undocumented endpoints or advertise them as enabled merely because environment variables
exist. SSI requires an authenticated integration test after account approval. FiinGroup
requires confirmation of the contracted product scope, entitlement and redistribution
rights. Until those checks pass, `enabled_capabilities` remains empty.

## Securities master

`app/data/securities_bootstrap.csv` is a visibly sourced, non-comprehensive bootstrap set. Operators can import an authorized CSV or XLSX; symbol, Vietnamese name/aliases, exchange, status, provider IDs and provenance are persisted without code changes. HNX provides an [official listing page](https://www.hnx.vn/co-phieu-etfs/chung-khoan-ny.html), but the application does not scrape it without confirmed automated-use and redistribution permission.

The Securities Explorer reads only that persisted registry through database-side filters,
sorting and pagination. Its latest price, change and volume come from the two latest valid
stored price observations; estimated trading value is latest close multiplied by latest
volume and is labeled as an estimate. P/E and P/B are returned only when those metrics
exist in stored financial data. Missing values remain null and are rendered as
`Chưa có dữ liệu`; the explorer never expands the bootstrap with generated companies or
generated market figures.

## Corporate actions and price quality

Authorized action exports can be stored with source, effective timestamp, ratio/cash amount and verification status. They are not automatically applied to historical prices. Price observations retain explicit adjusted/unadjusted provenance plus flags for zero volume, a jump over 20%, or a calendar gap over four days. The calendar-gap flag is a review signal, not proof of a missing session, because an official exchange holiday calendar is not yet connected.

## Financial statements

`POST /stocks/{symbol}/financials/import` accepts an authorized CSV with period, statement type, normalized item code, value, source, reporting and verification metadata. The system stores periods/items first, then calculates ratios from stored rows. No endpoint labels a manual/CSV source as live. A provider interface is reserved for FireAnt or another licensed feed; it remains disconnected until a real authorized request succeeds.

## VPS SmartOne

No connector is implemented. The product will prefer manual/CSV portfolio import until an official, documented, read-only integration is available. It will not reverse-engineer login or trading endpoints.

V4 source rule: a feed is operational only after a real request succeeds. `NEWS_FEEDS` may list authorized RSS URLs, but configured-only URLs are reported as unverified and do not count as live coverage. Yahoo remains a development source without a commercial licensing claim; FireAnt, VPS and live financial/social providers remain credential or entitlement dependent.

## Data-quality diagnostics

`GET /api/v1/data-quality` reports securities coverage, price and financial-statement coverage, stored observations, latest market/retrieval timestamps, sync errors, failed symbols and connector health. Migrations `0007` and `0013` retain connector health plus each ingestion run/error. The web dashboard presents `fixture`, `configured`, `available` and `unavailable` distinctly; configured sources without a verified successful request are not described as live.

## AI evidence boundary

External LLM responses are proposals, not a data source. A proposed financial claim is accepted only when its evidence ID resolves to the same security, metric, period and compatible unit/value. Forecasts additionally require evidence explicitly classified as a forecast. The application renders its own narrative from accepted claims and records rejected-claim limitations.
