@echo off
cd /d "D:\New folder\leather-shoes-wms"
chcp 65001 > nul
title KingsMan Leather Shoemaker - WMS
color 0b

echo ================================================
echo    HE THONG QUAN LY KHO GIAY DA KINGSMAN
echo    Truy cap: http://localhost:8000
echo    Nhan Ctrl + C de dung may chu
echo ================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [!] Chua tim thay .venv. Dang tao...
    python -m venv .venv
    .venv\Scripts\pip.exe install -r requirements.txt
)

echo [+] Khoi dong may chu...
.venv\Scripts\python.exe app.py
pause
