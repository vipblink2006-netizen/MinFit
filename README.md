# MinFit · Thẩm định dòng tiền BĐS

MinFit là ứng dụng Streamlit local hỗ trợ môi giới mô phỏng chính xác dòng tiền từng tháng và lọc dự án bằng quy tắc tài chính. Không sử dụng API AI hoặc Machine Learning.

## Chạy ứng dụng

Chỉ cần nhấp đúp file:

    D:\WebAnh\run_app.bat

File này tự động:

1. Dùng Python đã có trên máy.
2. Tạo môi trường riêng .venv nếu chưa tồn tại.
3. Cài Streamlit và pyodbc từ thư mục packages hoàn toàn offline nếu cần.
4. Kiểm tra hoặc khởi tạo database SQL Server local MinFitLocal.
5. Mở web local tại http://127.0.0.1:8501.

Không cần Internet, không chạy pip ra ngoài và không nhập lệnh thủ công. Toàn bộ wheel nằm trong thư mục packages; run_app.bat là file cài/chạy duy nhất.

### macOS

MinFit dùng SQLite local trên macOS, không cần SQL Server hay ODBC. Chạy:

    ./run_app.sh

Lần đầu chạy, script tự tạo `.venv` và cài Streamlit cùng Pandas nếu máy chưa có. Cơ sở dữ liệu SQLite được lưu tại `data/minfit.sqlite3` và tự nạp dữ liệu mẫu từ `data/projects.json`.

### React multi-page UI

Bản giao diện React Router mới chạy độc lập bằng Python static server, không cần cài Node/npm:

    ./run_frontend.sh

Sau đó mở `http://127.0.0.1:5173`. Giao diện gồm Trang chủ, Khách hàng, Kho Dự án và Dashboard Phân tích tại `/analysis/:id`. React dùng Tailwind CDN và mô phỏng DTI, FCF, PMT theo dữ liệu form để có thể demo ngay trên máy local.

## Chức năng

- Mô phỏng lịch trả nợ 120-360 tháng.
- Lãi suất hai giai đoạn: ưu đãi và thả nổi.
- Trả gốc đều hoặc trả gốc lãi đều Annuity.
- Không ân hạn, chỉ trả lãi, hoặc dồn lãi vào dư nợ.
- Tính từng tháng: dư nợ, tiền gốc, tiền lãi, PMT, DTI và FCF.
- Bộ lọc cứng: LTV trên 80%, DTI trên 50%, FCF âm hoặc thiếu vốn đối ứng.
- Phát hiện Payment Shock, Illusion of Safety và số tháng sinh tồn.
- Xếp hạng theo 4 chân dung khách hàng và 3 tiện ích bắt buộc.
- Xuất ảnh tư vấn A4, báo cáo tổng hợp TXT và lịch trả nợ CSV.

## Cấu trúc chính

- app.py: Dashboard Streamlit.
- loan_dti.py: Thuật toán khoản vay và timeline.
- project_engine.py: Bộ lọc, khoảng cách và xếp hạng.
- explanation_engine.py: Văn bản rule-based bằng if/else.
- database.py: Kết nối SQL Server bằng Windows Authentication và tự tạo schema.
- data/projects.json: Dữ liệu seed cho database, không phải nguồn đọc trực tiếp của web.
- SQL Server local: instance .\MINH, database MinFitLocal.
- tests/test_loan_dti.py: Kiểm thử thuật toán.
- run_app.bat: File duy nhất để cài môi trường và chạy web.

## Kiểm thử

    python -m unittest discover -s tests -v

Dữ liệu dự án và trọng số được đọc trực tiếp từ SQL Server local. Chỉ dữ liệu danh mục được lưu; MinFit không ghi thu nhập, khoản nợ hoặc chi phí khách hàng xuống database hay ổ cứng.
