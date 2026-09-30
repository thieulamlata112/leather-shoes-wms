# Hệ Thống Quản Lý Kho Giày Da Trực Tuyến (2 Kho & Ma Trận Size)

Phần mềm chuyên biệt cho các chủ shop thời trang, nhà xưởng và chuỗi bán lẻ **giày da cao cấp**, giúp giải quyết trọn vẹn bài toán:
1. **Ma trận Kích thước (Size 38 - 47)**: Nhập/xuất/chuyển kho nhanh chóng theo bảng size trực quan, không phải gõ từng dòng.
2. **Quản lý Đa Kho (Kho 1 & Kho 2)**: Theo dõi tồn kho độc lập tại Kho Tổng và Cửa hàng Showroom, luân chuyển hàng giữa 2 kho chỉ bằng 1 thao tác.
3. **Cảnh báo đứt gãy "Size Vàng" (39, 40, 41, 42)**: Nhắc nhở kịp thời các size phổ thông bán chạy nhất khi sắp cạn hàng.
4. **Quản lý Trực Tuyến Đa Thiết Bị (PC & Điện thoại)**: Tương thích hoàn hảo trên điện thoại di động (có thể quét mã vạch bằng camera) và máy tính PC/Laptop.
5. **Xuất Báo Cáo Excel**: Báo cáo tổng hợp tồn kho 2 kho và danh sách cảnh báo thiếu hàng ra file `.xlsx` định dạng đẹp mắt.

---

## 1. Hướng Dẫn Khởi Chạy Nhanh (1-Click)

1. Mở thư mục dự án:
   `C:\Users\Admin\.gemini\antigravity\scratch\leather-shoes-wms`
2. **Nhấp đúp chuột vào file `start.bat`**.
3. Trình duyệt trên máy tính sẽ tự động mở địa chỉ: `http://localhost:8000`.

---

## 2. Cách Sử Dụng Trên Điện Thoại Di Động (Quản Lý Trực Tuyến)

### Cách 1: Truy cập nội bộ cùng mạng Wi-Fi (Nhanh nhất & Miễn phí)
1. Kết nối điện thoại của bạn vào **cùng mạng Wi-Fi** với máy tính đang chạy phần mềm.
2. Trên màn hình máy tính, bấm nút **"Mở trên điện thoại"** ở góc trên cùng bên phải.
3. Một **mã QR** sẽ hiện ra: Bạn chỉ cần dùng Camera của iPhone (Safari) hoặc điện thoại Android quét mã để mở ngay giao diện phần mềm!
4. Hoặc bạn có thể gõ trực tiếp địa chỉ hiển thị (ví dụ: `http://192.168.100.129:8000`) vào trình duyệt web trên điện thoại.

### Cách 2: Truy cập từ xa mọi lúc mọi nơi qua 4G/5G / Internet (Cloudflare Tunnel)
Nếu bạn muốn khi đi ra ngoài đường, ở xưởng xa hoặc ở nhà vẫn mở được bằng 4G/5G trên điện thoại:
- Dùng công cụ **Cloudflare Tunnel (Cloudflared)** hoàn toàn **miễn phí 100%**:
  ```bash
  # Tải cloudflared và chạy lệnh:
  cloudflared tunnel --url http://localhost:8000
  ```
- Cloudflare sẽ cấp ngay cho bạn 1 đường link bảo mật HTTPS (ví dụ: `https://giay-da-kho.trycloudflare.com`) để bạn truy cập ở bất kỳ đâu trên thế giới!

---

## 3. Các Phân Hệ Chức Năng Chính

### 📊 1. Tổng Quan (Dashboard)
- 4 thẻ KPI: Tổng đôi giày trong hệ thống, Tồn tại Kho 1 (Kho Tổng), Tồn tại Kho 2 (Cửa Hàng), Tổng giá trị kho (theo giá vốn & giá bán lẻ).
- **Cảnh báo đứt gãy Size Vàng**: Tự động lọc ra các mẫu giày có size 39, 40, 41, 42 đang có số lượng ≤ 2 đôi hoặc hết sạch hàng (0 đôi).
- Danh sách biến động kho gần nhất.

### 📦 2. Kho Hàng & Bảng Ma Trận Size
- Bộ lọc kho: Xem riêng **Kho 1**, xem riêng **Kho 2** hoặc xem **Cả 2 Kho**.
- Bảng ma trận: Cột hiển thị từng kích cỡ từ 38 đến 47. Các ô size được đổi màu trực quan (Đỏ: Hết hàng, Vàng: Sắp hết, Xanh: An toàn).
- Nút thêm mới mẫu giày da với tính năng tự động sinh mã vạch Barcode/SKU cho toàn bộ các size từ 38 đến 47.

### 📥 3. Nhập Kho (Inbound)
- Chọn Kho nhận (Kho 1 hoặc Kho 2).
- Điền tên Xưởng sản xuất / Nhà cung cấp.
- Chọn mẫu giày -> Bảng dải size hiện ra -> Nhập số lượng từng size cần nhập -> Bấm **"Hoàn tất nhập kho"**.

### 📤 4. Xuất Kho / Bán Hàng (Outbound)
- Chọn Kho xuất (Kho 1 hoặc Kho 2).
- Chọn mẫu giày -> Hệ thống hiển thị số lượng tồn hiện có trong ngoặc để nhân viên không xuất nhầm.
- Có hệ thống kiểm tra chặn xuất âm nếu số lượng xuất lớn hơn tồn kho thực tế.

### 🔄 5. Điều Chuyển Kho (Transfer 1 ⇄ 2)
- Chọn Kho Gửi và Kho Nhận.
- Nhập số lượng các size cần luân chuyển.
- Hệ thống tự động khấu trừ kho gửi và cộng dồn vào kho nhận tức thì.

### 📋 6. Kiểm Kê & Cân Đối (Audit)
- Chọn kho kiểm tra và mẫu giày.
- Hệ thống hiển thị số lượng trên máy tính song song với ô nhập số lượng đếm thực tế.
- Tự động tính chênh lệch Thừa/Thiếu và cân đối lại kho chỉ với 1 click.

### 🔍 7. Quét Mã Vạch & Tra Cứu (Scanner)
- Hỗ trợ bật Camera điện thoại / Laptop để quét mã vạch trên vỏ hộp hoặc tag giày.
- Hoặc kết nối súng bắn mã vạch USB để tra cứu tức thì: Mẫu này còn bao nhiêu đôi ở Kho 1 và Kho 2!

### 📥 8. Xuất Báo Cáo Excel
- Tải file Excel `.xlsx` gồm 2 sheet chuyên nghiệp:
  1. Sheet Tồn kho ma trận size của cả 2 kho.
  2. Sheet Danh sách cảnh báo size thiếu hàng cần sản xuất thêm.

---

## 4. Công Nghệ Sử Dụng
- **Backend**: Python 3.13 + FastAPI + Uvicorn + SQLite3 + Openpyxl.
- **Frontend**: HTML5 Single Page Application + Tailwind CSS + Lucide Icons + Html5-Qrcode + QRCode.js.
- **Cơ sở dữ liệu**: SQLite file cục bộ (`warehouse.db`), an toàn, không lo mất dữ liệu, dễ dàng copy sao lưu.
