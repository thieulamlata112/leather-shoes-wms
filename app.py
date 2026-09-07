import os
import io
import socket
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import database

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

app = FastAPI(title="Hệ Thống Quản Lý Kho Giày Da Trực Tuyến", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---
class NewProductRequest(BaseModel):
    code: str
    name: str
    category: str = "Oxford"
    material: str = "Da bò"
    color: str = "Đen"
    cost_price: float = 0
    retail_price: float = 0
    min_stock_per_size: int = 2
    notes: Optional[str] = ""
    sizes: List[int] = [38, 39, 40, 41, 42, 43, 44]
    initial_stock_wh1: Dict[str, int] = {}
    initial_stock_wh2: Dict[str, int] = {}

class TransactionItemInput(BaseModel):
    variant_id: int
    size: int
    quantity: int
    unit_price: float = 0
    system_quantity: Optional[int] = None
    actual_quantity: Optional[int] = None

class CreateTransactionRequest(BaseModel):
    type: str # INBOUND, OUTBOUND, TRANSFER, AUDIT
    source_warehouse_id: Optional[int] = None
    target_warehouse_id: Optional[int] = None
    partner_name: Optional[str] = ""
    notes: Optional[str] = ""
    items: List[TransactionItemInput]

# --- Helper: Lấy địa chỉ IP mạng nội bộ ---
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# --- API Endpoints ---

@app.get("/api/network-info")
def get_network_info():
    local_ip = get_local_ip()
    port = 8000
    return {
        "local_ip": local_ip,
        "port": port,
        "local_url": f"http://localhost:{port}",
        "network_url": f"http://{local_ip}:{port}",
        "message": f"Mở trình duyệt trên điện thoại (cùng mạng Wi-Fi) và truy cập: http://{local_ip}:{port}"
    }

@app.get("/api/warehouses")
def list_warehouses():
    return database.get_warehouses()

@app.get("/api/products")
def list_products(warehouse_id: Optional[int] = None):
    return database.get_all_products_with_stock(warehouse_id)

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    prod = database.get_product_by_id(product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu giày này.")
    return prod

@app.post("/api/products")
def create_new_product(payload: NewProductRequest):
    try:
        new_prod = database.create_product(payload.dict())
        return {"success": True, "product": new_prod}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi khi thêm mẫu giày: {str(e)}")

@app.get("/api/barcode/lookup")
def lookup_barcode(code: str):
    res = database.lookup_barcode(code)
    if not res:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy thông tin cho mã: {code}")
    return res

@app.get("/api/dashboard")
def dashboard_stats():
    return database.get_dashboard_stats()

@app.post("/api/transactions")
def create_transaction(payload: CreateTransactionRequest):
    data = payload.dict()
    # Kiểm tra tính hợp lệ cơ bản
    t_type = data["type"].upper()
    if t_type == "INBOUND" and not data.get("target_warehouse_id"):
        raise HTTPException(status_code=400, detail="Vui lòng chọn Kho Nhận hàng.")
    if t_type == "OUTBOUND" and not data.get("source_warehouse_id"):
        raise HTTPException(status_code=400, detail="Vui lòng chọn Kho Xuất hàng.")
    if t_type == "TRANSFER":
        if not data.get("source_warehouse_id") or not data.get("target_warehouse_id"):
            raise HTTPException(status_code=400, detail="Vui lòng chọn cả Kho Gửi và Kho Nhận.")
        if data["source_warehouse_id"] == data["target_warehouse_id"]:
            raise HTTPException(status_code=400, detail="Kho Gửi và Kho Nhận không được trùng nhau.")
    if t_type == "AUDIT" and not data.get("target_warehouse_id"):
        raise HTTPException(status_code=400, detail="Vui lòng chọn Kho cần cân đối kiểm kê.")

    if not data.get("items") or len(data["items"]) == 0:
        raise HTTPException(status_code=400, detail="Danh sách mặt hàng trống.")

    try:
        res = database.execute_stock_transaction(data)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi thực hiện giao dịch kho: {str(e)}")

@app.get("/api/transactions")
def list_transactions(limit: int = 50, type: Optional[str] = None):
    return database.get_transactions_list(limit, type)

@app.post("/api/import/re-sync")
def resync_from_excel():
    try:
        import import_kingsman
        import_kingsman.run_import()
        return {"success": True, "message": "Đã đồng bộ lại toàn bộ dữ liệu từ file Excel KingsMan (1).xlsx thành công!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đồng bộ: {str(e)}")

# --- Xuất Báo Cáo Excel ---
@app.get("/api/export/excel")
def export_excel():
    wb = openpyxl.Workbook()
    
    # Header styling
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Dark Blue
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Arial", size=10, italic=True, color="555555")
    border_thin = Border(
        left=Side(style='thin', color='DDDDDD'),
        right=Side(style='thin', color='DDDDDD'),
        top=Side(style='thin', color='DDDDDD'),
        bottom=Side(style='thin', color='DDDDDD')
    )
    
    # Sheet 1: Báo Cáo Tồn Kho 2 Kho theo Ma Trận Size
    ws1 = wb.active
    ws1.title = "Ton_Kho_Ma_Tran_Size"
    
    ws1["A1"] = "BÁO CÁO TỒN KHO GIÀY DA - THEO MA TRẬN KÍCH CỠ"
    ws1["A1"].font = title_font
    ws1["A2"] = f"Thời gian xuất: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Quản lý: Kho 1 & Kho 2"
    ws1["A2"].font = subtitle_font
    
    ALL_SIZES = [38, 39, 40, 41, 42, 43, 44, 45, 46, 47]
    headers1 = [
        "Mã SKU", "Tên Mẫu Giày", "Chất Liệu", "Màu Sắc", "Kho Hàng",
        "Size 38", "Size 39", "Size 40", "Size 41", "Size 42", "Size 43", "Size 44", "Size 45", "Size 46", "Size 47",
        "Tổng Đôi", "Giá Vốn (VNĐ)", "Giá Bán (VNĐ)", "Tổng Giá Vốn", "Tổng Giá Bán"
    ]
    
    for col_num, header in enumerate(headers1, 1):
        cell = ws1.cell(row=4, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    products = database.get_all_products_with_stock()
    current_row = 5
    
    for p in products:
        # Lấy số tồn theo từng size
        sizes_map_wh1 = {}
        sizes_map_wh2 = {}
        sizes_map_all = {}
        
        for v in p["variants"]:
            sz = v["size"]
            sizes_map_wh1[sz] = v["stock_wh1"]
            sizes_map_wh2[sz] = v["stock_wh2"]
            sizes_map_all[sz] = v["stock_total"]
            
        # Dòng 1: Kho 1
        ws1.cell(row=current_row, column=1, value=p["code"])
        ws1.cell(row=current_row, column=2, value=p["name"])
        ws1.cell(row=current_row, column=3, value=p["material"])
        ws1.cell(row=current_row, column=4, value=p["color"])
        ws1.cell(row=current_row, column=5, value="Kho 1 (Kho Tổng - Ở Nhà)")
        for i, sz in enumerate(ALL_SIZES, 6):
            c = ws1.cell(row=current_row, column=i, value=sizes_map_wh1.get(sz, 0))
            c.alignment = Alignment(horizontal="center")
        col_tot = 6 + len(ALL_SIZES)
        ws1.cell(row=current_row, column=col_tot, value=p["stock_wh1_total"])
        ws1.cell(row=current_row, column=col_tot + 1, value=p["cost_price"])
        ws1.cell(row=current_row, column=col_tot + 2, value=p["retail_price"])
        ws1.cell(row=current_row, column=col_tot + 3, value=p["stock_wh1_total"] * p["cost_price"])
        ws1.cell(row=current_row, column=col_tot + 4, value=p["stock_wh1_total"] * p["retail_price"])
        current_row += 1
        
        # Dòng 2: Kho 2
        ws1.cell(row=current_row, column=1, value=p["code"])
        ws1.cell(row=current_row, column=2, value=p["name"])
        ws1.cell(row=current_row, column=3, value=p["material"])
        ws1.cell(row=current_row, column=4, value=p["color"])
        ws1.cell(row=current_row, column=5, value="Kho 2 (Cửa Hàng)")
        for i, sz in enumerate(ALL_SIZES, 6):
            c = ws1.cell(row=current_row, column=i, value=sizes_map_wh2.get(sz, 0))
            c.alignment = Alignment(horizontal="center")
        ws1.cell(row=current_row, column=col_tot, value=p["stock_wh2_total"])
        ws1.cell(row=current_row, column=col_tot + 1, value=p["cost_price"])
        ws1.cell(row=current_row, column=col_tot + 2, value=p["retail_price"])
        ws1.cell(row=current_row, column=col_tot + 3, value=p["stock_wh2_total"] * p["cost_price"])
        ws1.cell(row=current_row, column=col_tot + 4, value=p["stock_wh2_total"] * p["retail_price"])
        current_row += 1
        
        # Dòng 3: Tổng Cộng cả 2 kho (In đậm)
        ws1.cell(row=current_row, column=1, value=p["code"])
        ws1.cell(row=current_row, column=2, value=p["name"])
        ws1.cell(row=current_row, column=3, value=p["material"])
        ws1.cell(row=current_row, column=4, value=p["color"])
        ws1.cell(row=current_row, column=5, value="TỔNG 2 KHO")
        for i, sz in enumerate(ALL_SIZES, 6):
            c = ws1.cell(row=current_row, column=i, value=sizes_map_all.get(sz, 0))
            c.alignment = Alignment(horizontal="center")
            c.font = Font(bold=True)
        ws1.cell(row=current_row, column=col_tot, value=p["total_stock"]).font = Font(bold=True)
        ws1.cell(row=current_row, column=col_tot + 1, value=p["cost_price"])
        ws1.cell(row=current_row, column=col_tot + 2, value=p["retail_price"])
        ws1.cell(row=current_row, column=col_tot + 3, value=p["total_stock"] * p["cost_price"]).font = Font(bold=True)
        ws1.cell(row=current_row, column=col_tot + 4, value=p["total_stock"] * p["retail_price"]).font = Font(bold=True)
        
        for r_idx in range(current_row - 2, current_row + 1):
            for c_idx in range(1, col_tot + 5):
                ws1.cell(row=r_idx, column=c_idx).border = border_thin
        current_row += 1

    # Auto fit cột
    for col in ws1.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 11)

    # Sheet 2: Cảnh Báo Size Vàng Thiếu Hàng
    ws2 = wb.create_sheet(title="Canh_Bao_Size_Vang")
    ws2["A1"] = "DANH SÁCH CẢNH BÁO ĐỨT GÃY SIZE VÀNG (39, 40, 41, 42) & THIẾU HÀNG"
    ws2["A1"].font = title_font
    
    headers2 = ["Mã Giày", "Tên Mẫu", "Kích Cỡ", "Mã Vạch Barcode", "Kho Hàng", "Số Tồn Thực Tế", "Ngưỡng Cảnh Báo", "Tình Trạng"]
    for col_num, header in enumerate(headers2, 1):
        cell = ws2.cell(row=3, column=col_num)
        cell.value = header
        cell.fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid") # Red
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        
    stats = database.get_dashboard_stats()
    r2 = 4
    for item in stats["golden_size_alerts"] + stats["other_alerts"]:
        ws2.cell(row=r2, column=1, value=item["product_code"])
        ws2.cell(row=r2, column=2, value=item["product_name"])
        ws2.cell(row=r2, column=3, value=f"Size {item['size']}").alignment = Alignment(horizontal="center")
        ws2.cell(row=r2, column=4, value=item["barcode"])
        ws2.cell(row=r2, column=5, value=item["warehouse_name"])
        qty_cell = ws2.cell(row=r2, column=6, value=item["quantity"])
        qty_cell.alignment = Alignment(horizontal="center")
        qty_cell.font = Font(bold=True, color="DC2626" if item["quantity"] == 0 else "D97706")
        ws2.cell(row=r2, column=7, value=item["min_stock_per_size"]).alignment = Alignment(horizontal="center")
        status_txt = "HẾT HÀNG (0 đôi)" if item["quantity"] == 0 else f"Sắp hết ({item['quantity']} đôi)"
        ws2.cell(row=r2, column=8, value=status_txt)
        r2 += 1

    for col in ws2.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Lưu vào buffer byte
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    filename = f"Bao_Cao_Ton_Kho_Giay_Da_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Mount Static Frontend ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Hệ Thống Quản Lý Kho Giày Da đang khởi động...</h1>")

if __name__ == "__main__":
    import uvicorn
    # Lắng nghe trên 0.0.0.0 để điện thoại cùng mạng Wi-Fi có thể truy cập được
    print("=" * 60)
    print("  HE THONG QUAN LY KHO GIAY DA DANG CHAY")
    print(f"  - May tinh:    http://localhost:8000")
    print(f"  - Dien thoai:  http://{get_local_ip()}:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
