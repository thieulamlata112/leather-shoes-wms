import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(__file__), "warehouse.db")
SUPPORTED_SIZES = [38, 39, 40, 41, 42, 43, 44, 45, 46, 47]

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Bảng Kho Hàng (Warehouses)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        address TEXT,
        phone TEXT,
        is_default INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Bảng Mẫu Giày Da (Products)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,       -- Mã mẫu (SKU gốc, VD: GD-OXFORD-01)
        name TEXT NOT NULL,              -- Tên mẫu giày
        category TEXT DEFAULT 'Oxford',  -- Loại giày (Oxford, Derby, Loafer, Chelsea Boot...)
        material TEXT DEFAULT 'Da bò',   -- Chất liệu da (Da bò Ý, Da sáp, Da Nappa...)
        color TEXT DEFAULT 'Đen',        -- Màu sắc
        cost_price REAL DEFAULT 0,       -- Giá nhập (VNĐ)
        retail_price REAL DEFAULT 0,     -- Giá bán lẻ (VNĐ)
        min_stock_per_size INTEGER DEFAULT 2, -- Ngưỡng cảnh báo tồn tối thiểu mỗi size
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Bảng Biến Thể Size (Product Variants)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS product_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        size INTEGER NOT NULL,           -- Kích thước (38, 39, 40, 41, 42, 43, 44)
        barcode TEXT UNIQUE,             -- Mã vạch / QR từng size (VD: GD-OXFORD-01-40)
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
        UNIQUE(product_id, size)
    );
    """)

    # 4. Bảng Tồn Kho theo từng Kho & từng Size (Inventory)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        variant_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        quantity INTEGER DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE,
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE,
        UNIQUE(variant_id, warehouse_id)
    );
    """)

    # 5. Bảng Giao Dịch Kho (Transactions: Nhập, Xuất, Chuyển, Kiểm kê)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,       -- Mã phiếu (VD: PN-20260907-001, PX-..., PC-...)
        type TEXT NOT NULL,              -- 'INBOUND' (Nhập), 'OUTBOUND' (Xuất), 'TRANSFER' (Chuyển kho), 'AUDIT' (Kiểm kê)
        source_warehouse_id INTEGER,     -- Kho xuất / gửi
        target_warehouse_id INTEGER,     -- Kho nhập / nhận
        partner_name TEXT,               -- Nhà cung cấp / Khách hàng / Nhân viên
        customer_phone TEXT,             -- Số điện thoại khách hàng
        customer_address TEXT,           -- Địa chỉ giao hàng
        platform TEXT DEFAULT 'Khác',    -- Nền tảng bán hàng: Page, Voz, Tiktok, Shopee, Cho tot, Các nhóm, Khác
        purchase_count INTEGER DEFAULT 1,-- Số lần mua của khách hàng (Lần 1, Lần 2, Lần 3...)
        status TEXT DEFAULT 'COMPLETED', -- Trạng thái: 'COMPLETED' (Hoàn thành / Giao thành công), 'CANCELLED' (Đã hủy đơn)
        total_quantity INTEGER DEFAULT 0,
        total_amount REAL DEFAULT 0,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (source_warehouse_id) REFERENCES warehouses(id),
        FOREIGN KEY (target_warehouse_id) REFERENCES warehouses(id)
    );
    """)

    # Tự động nâng cấp bảng transactions nếu đã tồn tại nhưng thiếu các cột mới
    existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(transactions);").fetchall()]
    new_cols = [
        ("customer_phone", "TEXT"),
        ("customer_address", "TEXT"),
        ("platform", "TEXT DEFAULT 'Khác'"),
        ("purchase_count", "INTEGER DEFAULT 1"),
        ("status", "TEXT DEFAULT 'COMPLETED'")
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type};")

    # 6. Bảng Chi Tiết Giao Dịch theo từng Size (Transaction Items)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transaction_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL,
        variant_id INTEGER NOT NULL,
        size INTEGER NOT NULL,
        quantity INTEGER NOT NULL,       -- Số lượng biến động
        unit_price REAL DEFAULT 0,
        system_quantity INTEGER,         -- Dùng cho kiểm kê (số trên máy)
        actual_quantity INTEGER,         -- Dùng cho kiểm kê (số đếm thực tế)
        FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
        FOREIGN KEY (variant_id) REFERENCES product_variants(id)
    );
    """)

    conn.commit()
    seed_initial_data(conn)
    conn.close()

def seed_initial_data(conn):
    cursor = conn.cursor()
    # Kiểm tra xem đã có kho hàng chưa
    cursor.execute("SELECT COUNT(*) FROM warehouses;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO warehouses (code, name, address, phone, is_default) VALUES 
        ('KHO-01', 'Kho 1 - Kho Tổng (Hà Nội)', 'Số 120 Đường Láng, Đống Đa, Hà Nội', '0988.111.222', 1),
        ('KHO-02', 'Kho 2 - Cửa Hàng / Showroom (HCM)', 'Số 45 Lê Văn Sỹ, Quận 3, TP.HCM', '0977.333.444', 0);
        """)
        conn.commit()

    # Kiểm tra xem đã có sản phẩm mẫu chưa
    cursor.execute("SELECT COUNT(*) FROM products;")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            {
                "code": "GD-OXFORD-01",
                "name": "Giày Oxford Da Bò Ý Cổ Điển Cap-toe",
                "category": "Oxford",
                "material": "Da bò Ý trơn (Full Grain)",
                "color": "Đen Sang Trọng",
                "cost_price": 750000,
                "retail_price": 1450000,
                "min_stock": 2,
                "notes": "Dòng giày công sở cao cấp bán chạy nhất."
            },
            {
                "code": "GD-DERBY-02",
                "name": "Giày Derby Da Sáp Ngựa Điên (Crazy Horse)",
                "category": "Derby",
                "material": "Da bò sáp mộc",
                "color": "Nâu Vintage",
                "cost_price": 680000,
                "retail_price": 1290000,
                "min_stock": 2,
                "notes": "Chất da bụi bặm, bền bỉ, phối đồ jean/kaki."
            },
            {
                "code": "GD-LOAFER-03",
                "name": "Giày Penny Loafer Da Hạt Đế Phíp",
                "category": "Loafer",
                "material": "Da bò hạt (Pebble Grain)",
                "color": "Nâu Đậm Cafe",
                "cost_price": 620000,
                "retail_price": 1190000,
                "min_stock": 3,
                "notes": "Dáng xỏ tiện lợi, trẻ trung, lót da cừu êm chân."
            },
            {
                "code": "GD-CHELSEA-04",
                "name": "Chelsea Boot Da Bò Nappa Cổ Lửng",
                "category": "Boot",
                "material": "Da Nappa nhập khẩu",
                "color": "Đen Tuyển",
                "cost_price": 850000,
                "retail_price": 1650000,
                "min_stock": 2,
                "notes": "Chun co giãn 2 bên ôm chân, đế cao su đúc nguyên khối."
            }
        ]

        sizes = [38, 39, 40, 41, 42, 43, 44]
        
        # Tồn kho mẫu phân bổ giữa Kho 1 và Kho 2:
        initial_stock_distribution = {
            "GD-OXFORD-01": {
                38: (3, 1),
                39: (8, 3),
                40: (12, 4),
                41: (10, 5),
                42: (7, 2),
                43: (4, 1),
                44: (2, 0)
            },
            "GD-DERBY-02": {
                38: (2, 1),
                39: (6, 2),
                40: (9, 3),
                41: (1, 1), # Cảnh báo size 41 sắp hết
                42: (5, 2),
                43: (3, 1),
                44: (2, 1)
            },
            "GD-LOAFER-03": {
                38: (4, 2),
                39: (10, 4),
                40: (0, 1), # Kho 1 hết sạch size 40!
                41: (8, 3),
                42: (6, 2),
                43: (3, 1),
                44: (1, 1)
            },
            "GD-CHELSEA-04": {
                38: (3, 1),
                39: (5, 2),
                40: (8, 3),
                41: (7, 3),
                42: (4, 1),
                43: (2, 1),
                44: (1, 0)
            }
        }

        for sp in sample_products:
            cursor.execute("""
            INSERT INTO products (code, name, category, material, color, cost_price, retail_price, min_stock_per_size, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sp["code"], sp["name"], sp["category"], sp["material"], sp["color"], sp["cost_price"], sp["retail_price"], sp["min_stock"], sp["notes"]))
            product_id = cursor.lastrowid

            dist = initial_stock_distribution.get(sp["code"], {})

            for sz in sizes:
                barcode = f"{sp['code']}-{sz}"
                cursor.execute("""
                INSERT INTO product_variants (product_id, size, barcode)
                VALUES (?, ?, ?)
                """, (product_id, sz, barcode))
                variant_id = cursor.lastrowid

                wh1_qty, wh2_qty = dist.get(sz, (5, 2))
                # Kho 1 (id=1)
                cursor.execute("""
                INSERT INTO inventory (variant_id, warehouse_id, quantity)
                VALUES (?, 1, ?)
                """, (variant_id, wh1_qty))
                # Kho 2 (id=2)
                cursor.execute("""
                INSERT INTO inventory (variant_id, warehouse_id, quantity)
                VALUES (?, 2, ?)
                """, (variant_id, wh2_qty))

        # Tạo 1 giao dịch mẫu lịch sử
        cursor.execute("""
        INSERT INTO transactions (code, type, target_warehouse_id, partner_name, total_quantity, total_amount, notes, created_at)
        VALUES ('PN-INIT-001', 'INBOUND', 1, 'Xưởng Da Giày Phú Xuyên', 120, 85000000, 'Lô hàng đầu vụ Thu Đông nhập về Kho Tổng', datetime('now', '-2 days'))
        """)
        conn.commit()

# --- Query & Business Logic Functions ---

def get_warehouses():
    conn = get_db()
    rows = conn.execute("SELECT * FROM warehouses ORDER BY id ASC;").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_products_with_stock(warehouse_id: Optional[int] = None):
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC;").fetchall()
    
    result = []
    for p in products:
        p_dict = dict(p)
        # Lấy các biến thể size
        variants = conn.execute("""
            SELECT pv.id as variant_id, pv.size, pv.barcode
            FROM product_variants pv
            WHERE pv.product_id = ?
            ORDER BY pv.size ASC;
        """, (p["id"],)).fetchall()
        
        var_list = []
        total_qty = 0
        wh1_total = 0
        wh2_total = 0
        
        for v in variants:
            v_dict = dict(v)
            # Lấy tồn kho theo kho 1 và kho 2
            inv_rows = conn.execute("""
                SELECT warehouse_id, quantity 
                FROM inventory 
                WHERE variant_id = ?;
            """, (v["variant_id"],)).fetchall()
            
            wh_map = {row["warehouse_id"]: row["quantity"] for row in inv_rows}
            wh1_qty = wh_map.get(1, 0)
            wh2_qty = wh_map.get(2, 0)
            
            wh1_total += wh1_qty
            wh2_total += wh2_qty
            
            v_dict["stock_wh1"] = wh1_qty
            v_dict["stock_wh2"] = wh2_qty
            v_dict["stock_total"] = wh1_qty + wh2_qty
            
            if warehouse_id == 1:
                v_dict["display_quantity"] = wh1_qty
            elif warehouse_id == 2:
                v_dict["display_quantity"] = wh2_qty
            else:
                v_dict["display_quantity"] = wh1_qty + wh2_qty
                
            total_qty += v_dict["display_quantity"]
            var_list.append(v_dict)
            
        p_dict["variants"] = var_list
        p_dict["total_stock"] = total_qty
        p_dict["stock_wh1_total"] = wh1_total
        p_dict["stock_wh2_total"] = wh2_total
        result.append(p_dict)
        
    conn.close()
    return result

def get_product_by_id(product_id: int):
    conn = get_db()
    p = conn.execute("SELECT * FROM products WHERE id = ?;", (product_id,)).fetchone()
    if not p:
        conn.close()
        return None
    p_dict = dict(p)
    variants = conn.execute("""
        SELECT pv.id as variant_id, pv.size, pv.barcode
        FROM product_variants pv
        WHERE pv.product_id = ?
        ORDER BY pv.size ASC;
    """, (product_id,)).fetchall()
    
    var_list = []
    for v in variants:
        v_dict = dict(v)
        inv_rows = conn.execute("SELECT warehouse_id, quantity FROM inventory WHERE variant_id = ?;", (v["variant_id"],)).fetchall()
        wh_map = {row["warehouse_id"]: row["quantity"] for row in inv_rows}
        v_dict["stock_wh1"] = wh_map.get(1, 0)
        v_dict["stock_wh2"] = wh_map.get(2, 0)
        v_dict["stock_total"] = v_dict["stock_wh1"] + v_dict["stock_wh2"]
        var_list.append(v_dict)
    p_dict["variants"] = var_list
    conn.close()
    return p_dict

def lookup_barcode(code_str: str):
    """Tìm kiếm sản phẩm theo Barcode hoặc SKU hoặc mã sản phẩm"""
    conn = get_db()
    code_clean = code_str.strip()
    
    # 1. Thử tìm theo Barcode chính xác của biến thể (VD: GD-OXFORD-01-40)
    variant = conn.execute("""
        SELECT pv.*, p.code as product_code, p.name as product_name, p.category, p.color, p.material, p.retail_price, p.cost_price
        FROM product_variants pv
        JOIN products p ON p.id = pv.product_id
        WHERE pv.barcode = ? OR pv.barcode LIKE ?;
    """, (code_clean, f"%{code_clean}%")).fetchone()
    
    if variant:
        v_dict = dict(variant)
        inv_rows = conn.execute("SELECT warehouse_id, quantity FROM inventory WHERE variant_id = ?;", (v_dict["id"],)).fetchall()
        wh_map = {row["warehouse_id"]: row["quantity"] for row in inv_rows}
        v_dict["stock_wh1"] = wh_map.get(1, 0)
        v_dict["stock_wh2"] = wh_map.get(2, 0)
        v_dict["stock_total"] = v_dict["stock_wh1"] + v_dict["stock_wh2"]
        conn.close()
        return {"found_type": "variant", "data": v_dict}
        
    # 2. Thử tìm theo mã mẫu giày (VD: GD-OXFORD-01)
    product = conn.execute("""
        SELECT * FROM products WHERE code = ? OR code LIKE ? OR name LIKE ?;
    """, (code_clean, f"%{code_clean}%", f"%{code_clean}%")).fetchone()
    
    if product:
        p_id = product["id"]
        conn.close()
        return {"found_type": "product", "data": get_product_by_id(p_id)}
        
    conn.close()
    return None

def create_product(data: Dict[str, Any]):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT INTO products (code, name, category, material, color, cost_price, retail_price, min_stock_per_size, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["code"].strip().upper(),
        data["name"].strip(),
        data.get("category", "Oxford"),
        data.get("material", "Da bò"),
        data.get("color", "Đen"),
        float(data.get("cost_price", 0)),
        float(data.get("retail_price", 0)),
        int(data.get("min_stock_per_size", 2)),
        data.get("notes", "")
    ))
    product_id = cursor.lastrowid
    
    sizes = data.get("sizes", SUPPORTED_SIZES)
    initial_stock_wh1 = data.get("initial_stock_wh1", {}) # {38: 5, 39: 10...}
    initial_stock_wh2 = data.get("initial_stock_wh2", {})
    
    for sz in sizes:
        barcode = f"{data['code'].strip().upper()}-{sz}"
        cursor.execute("INSERT INTO product_variants (product_id, size, barcode) VALUES (?, ?, ?);", (product_id, sz, barcode))
        variant_id = cursor.lastrowid
        
        qty_wh1 = int(initial_stock_wh1.get(str(sz), initial_stock_wh1.get(sz, 0)))
        qty_wh2 = int(initial_stock_wh2.get(str(sz), initial_stock_wh2.get(sz, 0)))
        
        cursor.execute("INSERT INTO inventory (variant_id, warehouse_id, quantity) VALUES (?, 1, ?);", (variant_id, qty_wh1))
        cursor.execute("INSERT INTO inventory (variant_id, warehouse_id, quantity) VALUES (?, 2, ?);", (variant_id, qty_wh2))
        
    conn.commit()
    conn.close()
    return get_product_by_id(product_id)

def execute_stock_transaction(tx_data: Dict[str, Any]):
    """
    Xử lý giao dịch:
    - INBOUND: Nhập hàng vào kho target_warehouse_id
    - OUTBOUND: Xuất bán từ kho source_warehouse_id
    - TRANSFER: Chuyển hàng từ source_warehouse_id sang target_warehouse_id
    - AUDIT: Cân đối kiểm kê cho kho target_warehouse_id
    """
    conn = get_db()
    cursor = conn.cursor()

    def get_inventory_quantity(variant_id: int, warehouse_id: int) -> int:
        row = cursor.execute(
            """
            SELECT quantity
            FROM inventory
            WHERE variant_id = ? AND warehouse_id = ?;
            """,
            (variant_id, warehouse_id),
        ).fetchone()
        return int(row["quantity"]) if row else 0

    try:
        tx_type = tx_data["type"].upper()
        source_wh = tx_data.get("source_warehouse_id")
        target_wh = tx_data.get("target_warehouse_id")
        partner_name = tx_data.get("partner_name", "")
        customer_phone = tx_data.get("customer_phone")
        customer_address = tx_data.get("customer_address")
        platform = tx_data.get("platform", "Khác")
        purchase_count = int(tx_data.get("purchase_count", 1))
        status = tx_data.get("status", "COMPLETED")
        notes = tx_data.get("notes", "")
        items = tx_data.get("items", []) # [{variant_id, size, quantity, unit_price, actual_quantity}]

        # Tạo mã giao dịch tự động
        now_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix_map = {"INBOUND": "PN", "OUTBOUND": "PX", "TRANSFER": "PC", "AUDIT": "PK"}
        prefix = prefix_map.get(tx_type, "TX")
        tx_code = f"{prefix}-{now_str}"

        total_qty = 0
        total_amt = 0

        cursor.execute("""
        INSERT INTO transactions (
            code, type, source_warehouse_id, target_warehouse_id, partner_name,
            customer_phone, customer_address, platform, purchase_count, status,
            total_quantity, total_amount, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?);
        """, (
            tx_code, tx_type, source_wh, target_wh, partner_name,
            customer_phone, customer_address, platform, purchase_count, status,
            notes
        ))
        tx_id = cursor.lastrowid

        for item in items:
            variant_id = item["variant_id"]
            size = int(item["size"])
            qty = int(item["quantity"])
            price = 0.0 if tx_type == "TRANSFER" else float(item.get("unit_price", 0))
            system_qty = item.get("system_quantity")
            actual_qty = item.get("actual_quantity")

            if size not in SUPPORTED_SIZES:
                raise ValueError(f"Size {size} khong nam trong dai size duoc ho tro.")

            if tx_type in {"INBOUND", "OUTBOUND", "TRANSFER"} and qty <= 0:
                raise ValueError(f"So luong giao dich cho size {size} phai lon hon 0.")

            if tx_type == "AUDIT":
                if actual_qty is None:
                    raise ValueError(f"Thieu so luong thuc te cho size {size}.")
                actual_qty = int(actual_qty)
                if actual_qty < 0:
                    raise ValueError(f"So luong kiem ke thuc te cua size {size} khong duoc am.")

            if tx_type in {"OUTBOUND", "TRANSFER"}:
                available_qty = get_inventory_quantity(variant_id, source_wh)
                if qty > available_qty:
                    raise ValueError(
                        f"Size {size} tai kho {source_wh} chi con {available_qty} doi, khong the xuat/chuyen {qty} doi."
                    )

            total_qty += abs(qty)
            if tx_type != "TRANSFER":
                total_amt += abs(qty) * price

            # Ghi chi tiết item
            cursor.execute("""
            INSERT INTO transaction_items (transaction_id, variant_id, size, quantity, unit_price, system_quantity, actual_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (tx_id, variant_id, size, qty, price, system_qty, actual_qty))

            # Cập nhật tồn kho theo loại giao dịch
            if tx_type == "INBOUND":
                # Cộng tồn tại target_wh
                cursor.execute("""
                INSERT INTO inventory (variant_id, warehouse_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(variant_id, warehouse_id) DO UPDATE SET 
                quantity = quantity + excluded.quantity,
                updated_at = CURRENT_TIMESTAMP;
                """, (variant_id, target_wh, qty))

            elif tx_type == "OUTBOUND":
                # Trừ tồn tại source_wh
                cursor.execute("""
                UPDATE inventory 
                SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
                WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, variant_id, source_wh))

            elif tx_type == "TRANSFER":
                # Trừ tại source_wh, cộng tại target_wh
                cursor.execute("""
                UPDATE inventory 
                SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
                WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, variant_id, source_wh))

                cursor.execute("""
                INSERT INTO inventory (variant_id, warehouse_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(variant_id, warehouse_id) DO UPDATE SET 
                quantity = quantity + excluded.quantity,
                updated_at = CURRENT_TIMESTAMP;
                """, (variant_id, target_wh, qty))

            elif tx_type == "AUDIT":
                # Đặt lại số tồn chính xác bằng actual_quantity
                cursor.execute("""
                INSERT INTO inventory (variant_id, warehouse_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(variant_id, warehouse_id) DO UPDATE SET 
                quantity = excluded.quantity,
                updated_at = CURRENT_TIMESTAMP;
                """, (variant_id, target_wh, actual_qty))

        # Cập nhật lại tổng số lượng và tiền trên phiếu
        if tx_type == "TRANSFER":
            total_amt = 0
        cursor.execute("UPDATE transactions SET total_quantity = ?, total_amount = ? WHERE id = ?;", (total_qty, total_amt, tx_id))
        conn.commit()
        return {"success": True, "transaction_id": tx_id, "code": tx_code, "total_quantity": total_qty}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_customer_purchase_count(phone: Optional[str] = None, name: Optional[str] = None) -> int:
    """Đếm số lần khách đã mua hàng thành công trước đây (chỉ tính OUTBOUND và status != 'CANCELLED')."""
    conn = get_db()
    try:
        count = 0
        if phone:
            clean_phone = "".join(c for c in str(phone) if c.isdigit())
            if clean_phone:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM transactions 
                    WHERE type = 'OUTBOUND' AND status != 'CANCELLED' 
                    AND (customer_phone = ? OR notes LIKE ?);
                """, (clean_phone, f"%{clean_phone}%")).fetchone()
                count = row["cnt"] if row else 0
        elif name:
            clean_name = name.strip()
            if clean_name and len(clean_name) >= 3:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM transactions 
                    WHERE type = 'OUTBOUND' AND status != 'CANCELLED' 
                    AND partner_name LIKE ?;
                """, (f"%{clean_name}%",)).fetchone()
                count = row["cnt"] if row else 0
        return count + 1
    finally:
        conn.close()

def cancel_transaction(tx_id: int) -> Dict[str, Any]:
    """
    Hủy phiếu giao dịch và tự động hoàn trả tồn kho:
    - OUTBOUND: Cộng lại vào source_warehouse_id
    - INBOUND: Trừ lại ở target_warehouse_id
    - TRANSFER: Cộng lại ở source_warehouse_id, trừ ở target_warehouse_id
    - Đổi status = 'CANCELLED'
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        tx = cursor.execute("SELECT * FROM transactions WHERE id = ?;", (tx_id,)).fetchone()
        if not tx:
            raise ValueError("Không tìm thấy phiếu giao dịch cần hủy.")
        
        tx_dict = dict(tx)
        if tx_dict.get("status") == "CANCELLED":
            raise ValueError("Phiếu giao dịch này đã bị hủy trước đó.")

        tx_type = tx_dict["type"].upper()
        source_wh = tx_dict.get("source_warehouse_id")
        target_wh = tx_dict.get("target_warehouse_id")

        items = cursor.execute("SELECT * FROM transaction_items WHERE transaction_id = ?;", (tx_id,)).fetchall()

        for it in items:
            v_id = it["variant_id"]
            qty = it["quantity"]

            if tx_type == "OUTBOUND":
                # Trả lại kho xuất
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity = quantity + ?, updated_at = CURRENT_TIMESTAMP
                    WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, v_id, source_wh))

            elif tx_type == "INBOUND":
                # Trừ lại ở kho nhận
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
                    WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, v_id, target_wh))

            elif tx_type == "TRANSFER":
                # Hoàn trả kho xuất, trừ kho nhận
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity = quantity + ?, updated_at = CURRENT_TIMESTAMP
                    WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, v_id, source_wh))
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
                    WHERE variant_id = ? AND warehouse_id = ?;
                """, (qty, v_id, target_wh))

        cursor.execute("UPDATE transactions SET status = 'CANCELLED' WHERE id = ?;", (tx_id,))
        conn.commit()
        return {
            "success": True,
            "message": f"Đã hủy phiếu {tx_dict['code']} thành công và hoàn trả số lượng giày vào kho.",
            "transaction_id": tx_id,
            "code": tx_dict["code"]
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_dashboard_stats():
    conn = get_db()
    
    # 1. Tổng tồn toàn hệ thống
    total_pairs = conn.execute("SELECT COALESCE(SUM(quantity), 0) FROM inventory;").fetchone()[0]
    
    # 2. Tồn theo từng kho
    wh1_pairs = conn.execute("SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE warehouse_id = 1;").fetchone()[0]
    wh2_pairs = conn.execute("SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE warehouse_id = 2;").fetchone()[0]
    
    # 3. Giá trị kho theo giá vốn & giá bán lẻ
    val_rows = conn.execute("""
        SELECT 
            SUM(i.quantity * p.cost_price) as total_cost_value,
            SUM(i.quantity * p.retail_price) as total_retail_value
        FROM inventory i
        JOIN product_variants pv ON pv.id = i.variant_id
        JOIN products p ON p.id = pv.product_id;
    """).fetchone()
    
    total_cost_val = val_rows["total_cost_value"] or 0
    total_retail_val = val_rows["total_retail_value"] or 0
    
    # 4. Cảnh báo ĐỨT GÃY SIZE VÀNG (Size 39, 40, 41, 42) & Hết hàng
    # Điều kiện: size thuộc (39, 40, 41, 42) và số tồn <= ngưỡng cảnh báo min_stock_per_size (hoặc <= 2)
    low_stock_rows = conn.execute("""
        SELECT 
            p.id as product_id,
            p.code as product_code,
            p.name as product_name,
            pv.size,
            pv.barcode,
            w.id as warehouse_id,
            w.name as warehouse_name,
            i.quantity,
            p.min_stock_per_size
        FROM inventory i
        JOIN product_variants pv ON pv.id = i.variant_id
        JOIN products p ON p.id = pv.product_id
        JOIN warehouses w ON w.id = i.warehouse_id
        WHERE i.quantity <= p.min_stock_per_size
        ORDER BY i.quantity ASC, pv.size ASC;
    """).fetchall()
    
    golden_size_alerts = []
    other_alerts = []
    
    for r in low_stock_rows:
        item = dict(r)
        if item["size"] in [39, 40, 41, 42]:
            golden_size_alerts.append(item)
        else:
            other_alerts.append(item)
            
    # 5. Lịch sử 6 giao dịch gần nhất
    recent_txs = conn.execute("""
        SELECT 
            t.*,
            sw.name as source_warehouse_name,
            tw.name as target_warehouse_name
        FROM transactions t
        LEFT JOIN warehouses sw ON sw.id = t.source_warehouse_id
        LEFT JOIN warehouses tw ON tw.id = t.target_warehouse_id
        ORDER BY t.created_at DESC
        LIMIT 6;
    """).fetchall()
    
    conn.close()
    
    return {
        "total_pairs": total_pairs,
        "wh1_pairs": wh1_pairs,
        "wh2_pairs": wh2_pairs,
        "total_cost_value": total_cost_val,
        "total_retail_value": total_retail_val,
        "golden_size_alerts": golden_size_alerts,
        "other_alerts": other_alerts,
        "recent_transactions": [dict(t) for t in recent_txs]
    }

def get_transactions_list(limit: int = 50, tx_type: Optional[str] = None):
    conn = get_db()
    query = """
        SELECT 
            t.*,
            sw.name as source_warehouse_name,
            tw.name as target_warehouse_name
        FROM transactions t
        LEFT JOIN warehouses sw ON sw.id = t.source_warehouse_id
        LEFT JOIN warehouses tw ON tw.id = t.target_warehouse_id
    """
    params = []
    if tx_type:
        query += " WHERE t.type = ?"
        params.append(tx_type)
    query += " ORDER BY t.created_at DESC LIMIT ?;"
    params.append(limit)
    
    txs = conn.execute(query, params).fetchall()
    result = []
    for tx in txs:
        t_dict = dict(tx)
        items = conn.execute("""
            SELECT 
                ti.*,
                p.code as product_code,
                p.name as product_name
            FROM transaction_items ti
            JOIN product_variants pv ON pv.id = ti.variant_id
            JOIN products p ON p.id = pv.product_id
            WHERE ti.transaction_id = ?;
        """, (tx["id"],)).fetchall()
        t_dict["items"] = [dict(it) for it in items]
        result.append(t_dict)
    conn.close()
    return result
