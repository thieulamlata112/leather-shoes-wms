@echo off
chcp 65001 > nul
title Hệ Thống Quản Lý Kho Giày Da Trực Tuyến
color 0b

echo ======================================================================
echo    HỆ THỐNG QUẢN LÝ KHO GIÀY DA TRỰC TUYẾN (2 KHO & MA TRẬN SIZE)
echo ======================================================================
echo.
echo  Đang khởi động máy chủ quản lý kho...

if not exist ".venv\Scripts\python.exe" (
    echo [!] Chưa tìm thấy môi trường ảo .venv. Đang tự động tạo...
    python -m venv .venv
    .venv\Scripts\pip.exe install -r requirements.txt
)

echo  [+] Đang mở trình duyệt vào hệ thống...
start http://localhost:8000

echo.
echo  Máy chủ đang chạy tại:
echo    - Máy tính hiện tại: http://localhost:8000
echo.
echo  (Để mở trên điện thoại, vui lòng kết nối cùng mạng Wi-Fi và xem mã QR trên web)
echo.
echo  Nhấn Ctrl + C để dừng máy chủ khi không sử dụng.
echo ======================================================================
echo.

.venv\Scripts\python.exe app.py
pause
