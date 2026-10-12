# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Nhà đầu tư và người làm nghiên cứu thị trường chứng khoán Việt Nam cần khám phá doanh nghiệp, kiểm tra dữ liệu nguồn và đi từ quan sát tới luận điểm mà không phải biết trước mọi mã cổ phiếu.

## Product Purpose

Mạch Thị Trường là bàn nghiên cứu chỉ đọc: cho phép khám phá securities master, xem dữ liệu giá và nền tảng có nguồn, tính các chỉ tiêu xác định và mở báo cáo phân tích cho từng mã. Thành công nghĩa là người dùng tìm được doanh nghiệp phù hợp, hiểu độ phủ dữ liệu và không nhầm dữ liệu thiếu với số ước đoán.

## Positioning

Mọi số liệu tài chính phải đến từ connector hoặc công thức xác định, kèm provenance và timestamp; dữ liệu thiếu được nói rõ thay vì được bịa hoặc lấp bằng mô hình ngôn ngữ.

## Operating Context

Người dùng bắt đầu từ danh mục chứng khoán hoặc ô tìm kiếm, lọc theo sàn/ngành/trạng thái, rồi mở bàn nghiên cứu chi tiết. Hệ thống phục vụ nghiên cứu và không đặt lệnh giao dịch.

## Capabilities and Constraints

- FastAPI, SQLAlchemy và Next.js là stack hiện có.
- Danh mục phải phân trang, lọc và sắp xếp trong cơ sở dữ liệu.
- Securities master bootstrap hiện có 13 mã; chỉ nguồn nhập CSV/XLSX được phép mới được mở rộng registry.
- Fixture phải được dán nhãn rõ và không được chọn ngầm trong production.
- Ghi dữ liệu dùng chung cần quyền admin và audit; không đưa secret quản trị vào trình duyệt.
- FireAnt, VPS và các feed thương mại chỉ được coi là khả dụng sau khi có credential, entitlement và lần gọi thành công được xác minh.

## Brand Commitments

Tên sản phẩm là “Mạch Thị Trường”. Nội dung cho người dùng viết bằng tiếng Việt, giọng điệu rõ ràng, trung lập và phân biệt nghiên cứu với khuyến nghị đầu tư.

## Evidence on Hand

- Registry bootstrap có nguồn tại `apps/api/app/data/securities_bootstrap.csv`.
- Price observations, financial metrics và provenance được lưu trong database hiện tại.
- Không có bằng chứng về feed toàn thị trường được cấp phép; sản phẩm không được tuyên bố độ phủ hàng nghìn mã.

## Product Principles

- Dữ liệu thật trước độ phủ bề ngoài.
- Thiếu dữ liệu là một trạng thái sản phẩm cần hiển thị.
- Tác vụ khám phá phải hoạt động trước khi người dùng biết mã.
- Mọi phân tích quan trọng phải truy ngược được tới evidence.
- Giữ đường ranh rõ ràng giữa nghiên cứu và giao dịch.
