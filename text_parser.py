"""Module phân tích cú pháp văn bản tự nhiên toàn năng cho hệ thống quản lý kho giày da Kingsman.
Hỗ trợ:
- Nhận diện không phụ thuộc thứ tự các trường: Tên, SĐT, Địa chỉ, Mã giày, Size, Giá, Nền tảng, Kho.
- Tự động chuyển đổi giá 3-4 chữ số (VD: 890 -> 890.000, 1500 -> 1.500.000).
- Nhận diện 3 nghiệp vụ: Xuất bán (OUTBOUND), Nhập hàng (INBOUND), Chuyển kho (TRANSFER).
- Nhận diện Nền tảng bán hàng: Page, Voz, Tiktok, Shopee, Cho tot, Các nhóm, Khác.
- Tự động tra cứu số lần mua của khách hàng (Lần 1, Lần 2, Lần 3...).
"""
import re
import sqlite3
import os
from typing import Dict, Any, Optional, List, Tuple
import database

DB_PATH = os.path.join(os.path.dirname(__file__), "warehouse.db")
SUPPORTED_SIZES = database.SUPPORTED_SIZES

# Danh sách từ khóa nhận diện địa chỉ Việt Nam (tỉnh thành, quận huyện, hành chính)
ADDRESS_KEYWORDS = [
    "đường", "duong", "phố", "pho", "ngõ", "ngo", "ngách", "ngach", "hẻm", "hem",
    "số", "so", "nhà", "nha", "tầng", "tang", "chung cư", "toà", "tòa", "kđt",
    "phường", "phuong", "xã", "xa", "thị trấn", "thi tran", "thôn", "thon", "ấp", "ap",
    "quận", "quan", "huyện", "huyen", "thị xã", "thi xa", "tp", "thành phố", "thanh pho", "tỉnh", "tinh",
    # Các thành phố và tỉnh thành phổ biến
    "hà nội", "ha noi", "hồ chí minh", "ho chi minh", "hcm", "sài gòn", "sai gon",
    "đà nẵng", "da nang", "hải phòng", "hai phong", "cần thơ", "can tho", "huế", "hue",
    "đà lạt", "da lat", "lâm đồng", "lam dong", "nha trang", "khánh hòa", "khanh hoa",
    "bình dương", "binh duong", "đồng nai", "dong nai", "vũng tàu", "vung tau", "bà rịa",
    "quảng nam", "quang nam", "quảng ninh", "quang ninh", "hạ long", "thanh hóa", "thanh hoa",
    "nghệ an", "vinh", "hà tĩnh", "quảng bình", "bình định", "quy nhơn", "phú yên",
    "bắc ninh", "bắc giang", "hải dương", "hưng yên", "hà nam", "nam định", "ninh bình",
    "thái bình", "thái nguyên", "vĩnh phúc", "phú thọ", "hòa bình", "lào cai", "yên bái",
    "an giang", "kiên giang", "tiền giang", "bến tre", "long an", "đồng tháp", "tây ninh",
    "cầu giấy", "đống đa", "ba đình", "hoàn kiếm", "hai bà trưng", "thanh xuân", "hà đông",
    "hoàng mai", "từ liêm", "tây hồ", "thanh khê", "hải châu", "sơn trà", "ngũ hành sơn",
    "quận 1", "quận 2", "quận 3", "quận 7", "bình thạnh", "tân bình", "gò vấp", "thủ đức"
]

PLATFORM_KEYWORDS = [
    ("Tiktok", [r"\btiktok\b", r"\btik\s*tok\b", r"\btt\b"]),
    ("Shopee", [r"\bshopee\b", r"\bshope\b", r"\bshp\b"]),
    ("Voz", [r"\bvoz\b", r"\bvozer\b"]),
    ("Cho tot", [r"\bchợ\s*tốt\b", r"\bcho\s*tot\b", r"\bchotot\b"]),
    ("Các nhóm", [r"\bcác\s*nhóm\b", r"\bcac\s*nhom\b", r"\bnhóm\b", r"\bnhom\b", r"\bgroup\b"]),
    ("Page", [r"\bpage\b", r"\bfanpage\b", r"\bfb\b", r"\bfacebook\b"])
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def normalize_vietnamese(text: str) -> str:
    """Chuẩn hóa văn bản tiếng Việt: bỏ dấu, chữ thường."""
    import unicodedata
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize('NFD', text)
    no_diacritics = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return no_diacritics.lower()


def get_all_products():
    """Lấy danh sách tất cả sản phẩm từ DB kèm giá bán và tên."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, code, name, category, color, material, retail_price, cost_price FROM products").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_variant_with_stock(product_id: int, size: int):
    """Lấy thông tin biến thể và tồn kho của từng kho."""
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT pv.id as variant_id, pv.size, pv.barcode,
                   COALESCE(SUM(CASE WHEN i.warehouse_id = 1 THEN i.quantity ELSE 0 END), 0) as stock_wh1,
                   COALESCE(SUM(CASE WHEN i.warehouse_id = 2 THEN i.quantity ELSE 0 END), 0) as stock_wh2
            FROM product_variants pv
            LEFT JOIN inventory i ON i.variant_id = pv.id
            WHERE pv.product_id = ? AND pv.size = ?
            GROUP BY pv.id, pv.size, pv.barcode
        """, (product_id, size)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def extract_platform(text: str) -> str:
    """Nhận diện nền tảng bán hàng từ nội dung."""
    for platform_name, patterns in PLATFORM_KEYWORDS:
        for p in patterns:
            if re.search(p, text, re.I):
                return platform_name
    return "Khác"


def extract_phone(text: str) -> Tuple[Optional[str], str]:
    """Tìm số điện thoại và loại bỏ khỏi chuỗi để tránh xung đột giá/size."""
    phone = None
    remaining_text = text

    # Mẫu 1: Có tiền tố sdt / phone / tel
    m1 = re.search(r'(?:sdt|số điện thoại|điện thoại|phone|tel)[\s:]*([0-9\.\s]{9,15})', text, re.I)
    if m1:
        raw_digits = re.sub(r'[^\d]', '', m1.group(1))
        if len(raw_digits) in [10, 11] and raw_digits.startswith('0'):
            phone = raw_digits
            remaining_text = text[:m1.start()] + " " + text[m1.end():]
            return phone, remaining_text

    # Mẫu 2: Số điện thoại chuẩn VN (03, 05, 07, 08, 09 + 8 số)
    m2 = re.search(r'\b(0[35789]\d{8})\b', text)
    if m2:
        phone = m2.group(1)
        remaining_text = text[:m2.start()] + " " + text[m2.end():]
        return phone, remaining_text

    # Mẫu 3: Bất kỳ chuỗi 10 số bắt đầu bằng 0
    m3 = re.search(r'\b(0\d{9})\b', text)
    if m3:
        phone = m3.group(1)
        remaining_text = text[:m3.start()] + " " + text[m3.end():]
        return phone, remaining_text

    return None, remaining_text


def extract_product_and_items(text: str, all_products: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, int]], str]:
    """
    Trích xuất mã sản phẩm và danh sách các biến thể (size, số lượng).
    Hỗ trợ cả trường hợp 1 size đơn lẻ lẫn nhiều size trong 1 câu:
    Ví dụ:
    - 'WTN 38 5 đôi. 40 3 đôi 43 2 đôi vào cửa hàng'
    - 'nhập kho WTN size 38 5 đôi'
    - 'WTN 38x5 40x3 43x2'
    - '5 đôi 38, 3 đôi 40, 2 đôi 43'
    - 'CTD 43 890K'
    """
    matched_prod = None
    remaining = text

    # Sắp xếp mã sản phẩm theo độ dài giảm dần
    sorted_prods = sorted(all_products, key=lambda p: len(p['code']), reverse=True)

    # 1. Tìm mã sản phẩm
    for p in sorted_prods:
        code_esc = re.escape(p['code'])
        pattern = rf'(?:\b|đôi\s+|giày\s+|mã\s+)({code_esc})(?:\b|\s+|$)'
        m = re.search(pattern, remaining, re.I)
        if m:
            matched_prod = p
            remaining = remaining[:m.start(1)] + " " + remaining[m.end(1):]
            break

    if not matched_prod:
        for p in sorted_prods:
            if re.search(r'\b' + re.escape(p['code']) + r'\b', remaining, re.I):
                matched_prod = p
                remaining = re.sub(r'\b' + re.escape(p['code']) + r'\b', " ", remaining, flags=re.I, count=1)
                break

    items: List[Dict[str, int]] = []

    # 2. Mẫu 1: [size] <size> <số> (đôi/cặp/chiếc/c)
    # VD: '38 5 đôi', 'size 38 5 đôi', '40 3 đôi', '43 2 đôi', '38: 5 đôi', '38 x 5 đôi'
    p1 = r'(?:size|sz|cỡ)?\s*(3[8-9]|4[0-7])\s*[:x\-=,\s]?\s*(\d+)\s*(?:đôi|doi|cặp|cap|chiếc|chiec|c)\b'
    matches1 = list(re.finditer(p1, remaining, re.I))
    for m in reversed(matches1):
        sz = int(m.group(1))
        qty = int(m.group(2))
        if qty > 0:
            items.insert(0, {"size": sz, "quantity": qty})
            remaining = remaining[:m.start()] + " " + remaining[m.end():]

    # 3. Mẫu 2: <số> (đôi/cặp/chiếc) [size] <size> (VD: '5 đôi size 38', '3 đôi 40')
    p2 = r'(\d+)\s*(?:đôi|doi|cặp|cap|chiếc|chiec|c)\s*(?:size|sz|cỡ)?\s*[:\-\s]?\s*(3[8-9]|4[0-7])\b'
    matches2 = list(re.finditer(p2, remaining, re.I))
    for m in reversed(matches2):
        qty = int(m.group(1))
        sz = int(m.group(2))
        if qty > 0 and not any(it["size"] == sz for it in items):
            items.insert(0, {"size": sz, "quantity": qty})
            remaining = remaining[:m.start()] + " " + remaining[m.end():]

    # 4. Mẫu 3: Dạng 38x5, 40x3, 43-2, 43: 2, size 38: 5
    p3 = r'(?:size|sz|cỡ)?\s*(3[8-9]|4[0-7])\s*[:x\-]\s*(\d+)\b'
    matches3 = list(re.finditer(p3, remaining, re.I))
    for m in reversed(matches3):
        sz = int(m.group(1))
        qty = int(m.group(2))
        if qty > 0 and not any(it["size"] == sz for it in items):
            items.insert(0, {"size": sz, "quantity": qty})
            remaining = remaining[:m.start()] + " " + remaining[m.end():]

    # 5. Mẫu 4: Dạng chuỗi không có chữ đôi (VD: '38 5, 40 3, 43 2' hoặc '38 5. 40 3 43 2')
    if not items:
        p4 = r'(?<![/0-9\-])\b(3[8-9]|4[0-7])\s*[:,\-\s]\s*([1-9]\d?)\b(?![/0-9\-])'
        matches4 = list(re.finditer(p4, remaining, re.I))
        if len(matches4) >= 2:
            for m in reversed(matches4):
                sz = int(m.group(1))
                qty = int(m.group(2))
                items.insert(0, {"size": sz, "quantity": qty})
                remaining = remaining[:m.start()] + " " + remaining[m.end():]

    # 6. Mẫu đơn truyền thống: Tìm 1 size duy nhất
    if not items:
        m_sz = re.search(r'(?:size|sz|cỡ|kích\s*cỡ)\s*[:\-\s]?\s*(3[8-9]|4[0-7])\b', remaining, re.I)
        if m_sz:
            sz = int(m_sz.group(1))
            remaining = remaining[:m_sz.start()] + " " + remaining[m_sz.end():]
            items.append({"size": sz, "quantity": 1})
        else:
            candidates = list(re.finditer(r'(?<![/0-9\-])\b(3[8-9]|4[0-7])\b(?![/0-9\-])', remaining))
            if candidates:
                cand = candidates[-1]
                sz = int(cand.group(1))
                remaining = remaining[:cand.start()] + " " + remaining[cand.end():]
                items.append({"size": sz, "quantity": 1})

    # Nếu chỉ có 1 item và số lượng là 1, kiểm tra số lượng chung (vd: 2 đôi, 5 đôi)
    if len(items) == 1 and items[0]["quantity"] == 1:
        m_g = re.search(r'\b(\d+)\s*(?:đôi|doi|cặp|cap|chiếc|chiec)\b', remaining, re.I)
        if m_g:
            items[0]["quantity"] = int(m_g.group(1))
            remaining = remaining[:m_g.start()] + " " + remaining[m_g.end():]

    return matched_prod, items, remaining


def extract_product_and_size(text: str, all_products: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[int], str]:
    """Hàm bọc tương thích ngược với code cũ."""
    matched_prod, items, remaining = extract_product_and_items(text, all_products)
    size = items[0]["size"] if items else None
    return matched_prod, size, remaining


def extract_price(text: str) -> Tuple[Optional[float], str]:
    """
    Trích xuất giá tiền với quy tắc thông minh:
    - 890k, 1500k -> 890.000, 1.500.000
    - 1tr5 -> 1.500.000
    - 3-4 chữ số độc lập hoặc < 10000 (VD: 890, 1500, 450) -> nhân 1000 tự động!
    """
    remaining = text
    price = None

    # Mẫu 1: Dạng 1tr5, 1 triệu 5, 2tr
    m_tr = re.search(r'\b(\d+)\s*(?:tr|triệu)\s*(\d{1,3})?\b', remaining, re.I)
    if m_tr:
        trieu = float(m_tr.group(1)) * 1000000
        tram = float(m_tr.group(2) or 0)
        if tram > 0:
            if tram < 10:
                trieu += tram * 100000
            elif tram < 100:
                trieu += tram * 10000
            else:
                trieu += tram * 1000
        price = trieu
        remaining = remaining[:m_tr.start()] + " " + remaining[m_tr.end():]
        return price, remaining

    # Mẫu 2: Có đơn vị k, nghìn, ngàn, đ, vnđ (VD: 890K, 1500k, 890.000đ)
    m_unit = re.search(r'\b([\d\.,]+)\s*(k|nghìn|ngàn|đ|vnd)\b', remaining, re.I)
    if m_unit:
        raw_val = m_unit.group(1).replace('.', '').replace(',', '')
        if raw_val.isdigit():
            val = float(raw_val)
            unit = m_unit.group(2).lower()
            if unit in ['k', 'nghìn', 'ngàn']:
                val *= 1000
            elif val < 10000:
                val *= 1000
            price = val
            remaining = remaining[:m_unit.start()] + " " + remaining[m_unit.end():]
            return price, remaining

    # Mẫu 3: Có tiền tố giá / giá bán / tiền (VD: giá 1500, giá 890)
    m_prefix = re.search(r'(?:giá|gia|tiền|đơn giá|với giá)[\s:]*([\d\.,]+)', remaining, re.I)
    if m_prefix:
        raw_val = m_prefix.group(1).replace('.', '').replace(',', '')
        if raw_val.isdigit():
            val = float(raw_val)
            if val < 10000:
                val *= 1000
            price = val
            remaining = remaining[:m_prefix.start()] + " " + remaining[m_prefix.end():]
            return price, remaining

    # Mẫu 4: Số độc lập 3-4 chữ số (quy tắc user: 890 -> 890.000, 1500 -> 1.500.000)
    # Tìm các số có 3-4 chữ số không nằm trong số nhà hoặc ngày tháng
    m_nums = list(re.finditer(r'(?<![/0-9\-])\b(\d{3,4})\b(?![/0-9\-])', remaining))
    if m_nums:
        # Lấy số cuối cùng xuất hiện (thường giá để ở cuối lệnh bán)
        cand = m_nums[-1]
        val = float(cand.group(1))
        # Không nhầm với các số năm hoặc số size
        if val not in SUPPORTED_SIZES:
            price = val * 1000
            remaining = remaining[:cand.start()] + " " + remaining[cand.end():]
            return price, remaining

    # Mẫu 5: Số lớn đầy đủ 5-8 chữ số (VD: 1500000, 890000)
    m_big = list(re.finditer(r'(?<![/0-9\-])\b(\d{5,8})\b(?![/0-9\-])', remaining))
    if m_big:
        cand = m_big[-1]
        price = float(cand.group(1))
        remaining = remaining[:cand.start()] + " " + remaining[cand.end():]
        return price, remaining

    return None, remaining


def extract_quantity(text: str) -> Tuple[int, str]:
    """Trích xuất số lượng hàng hóa (mặc định 1)."""
    remaining = text
    qty = 1

    m1 = re.search(r'\b(\d+)\s*(?:đôi|cặp|chiec|chiếc)\b', remaining, re.I)
    if m1:
        qty = int(m1.group(1))
        remaining = remaining[:m1.start()] + " " + remaining[m1.end():]
        return qty, remaining

    m2 = re.search(r'(?:số\s*lượng|sl|so\s*luong|\bx)\s*[:=]?\s*(\d+)', remaining, re.I)
    if m2:
        qty = int(m2.group(1))
        remaining = remaining[:m2.start()] + " " + remaining[m2.end():]
        return qty, remaining

    return qty, remaining


def extract_name_and_address(original_text: str, remaining_text: str, tx_type: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Bóc tách Tên khách hàng và Địa chỉ.
    - Với INBOUND: partner_name là Nhà cung cấp/Xưởng, address = None.
    - Với TRANSFER: partner_name là Điều chuyển nội bộ, address = None.
    - Với OUTBOUND: Ưu tiên nhận diện theo mẫu từ khóa trên chuỗi gốc, sau đó fallback sang phân tích tự do không cố định vị trí.
    """
    if tx_type == "INBOUND":
        m_sup = re.search(r'(?:từ|nhà cung cấp|ncc|xưởng)[\s:]+([^,;\n]+)', original_text, re.I)
        name = m_sup.group(1).strip().title() if m_sup else "Nhà cung cấp / Xưởng sản xuất"
        return name, None

    if tx_type == "TRANSFER":
        return "Điều chuyển nội bộ", None

    name = None
    address = None

    # 1. Thử nhận diện theo cấu trúc từ khóa trên chuỗi gốc
    m_name = re.search(
        r'(?:bán\s+cho|xuất\s+cho|khách\s+hàng|khách|tên)[\s:]+([^,;\n]+?)(?=(?:\s+(?:sdt|số điện thoại|điện thoại|phone|địa chỉ|đ/c|đc|ở|tại|đôi giày|đôi|giày|mã|size|sz|cỡ|giá|tiền|qua|nền tảng|\b0[3-9]\d{8}\b))|$)',
        original_text,
        re.I
    )
    if m_name:
        cand = m_name.group(1).strip(" ,.-:")
        if cand and len(cand) <= 50 and not any(kw in cand.lower() for kw in ["địa chỉ", "kho", "sdt"]):
            name = cand.title()

    if not name:
        m_name2 = re.search(
            r'\b(?:cho|khách)\s+(?:anh|chị|em|bạn|bác|cô|chú)?\s*([a-zA-ZÀ-ỹ\s]{2,30}?)(?=(?:\s+(?:sdt|số|địa|ở|tại|đôi|giày|mã|size|giá|qua|tiktok|shopee|voz|\b0[3-9]\d{8}\b))|$)',
            original_text,
            re.I
        )
        if m_name2:
            cand = m_name2.group(1).strip(" ,.-:")
            if cand and len(cand) <= 50 and not any(kw in cand.lower() for kw in ["địa chỉ", "kho", "sdt"]):
                name = cand.title()

    def clean_addr_str(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        res = re.sub(r'^(?:ở|tại|đ/c|đc|địa chỉ)\s*[:\-]?', '', raw, flags=re.I)
        res = re.sub(r'\s*(?:lấy|lay|nhận|nhan|đôi|doi|giày|giay|hàng|hang|nhé|nha|ạ)\s*$', '', res, flags=re.I).strip(" ,.-:")
        return res if len(res) > 1 else None

    m_addr = re.search(
        r'(?:địa\s+chỉ|đ/c|đc|ở|tại)[\s:]+([^;\n]+?)(?=(?:\s+(?:đôi\s+giày|đôi|giày|mã|size|sz|cỡ|giá|tiền|sdt|số điện thoại|phone|sl|số lượng|qua|nền tảng))|$)',
        original_text,
        re.I
    )
    if m_addr:
        cand = m_addr.group(1).strip(" ,.-:")
        address = clean_addr_str(cand)

    if name and address:
        return name, address

    # 2. Phân tích tự do không cố định vị trí trên remaining_text (ví dụ: 'Trần Minh Trí, 103/1 Cù Chính Lan, Thanh Khê, Đà Nẵng')
    clean_rem = remaining_text
    if address:
        clean_rem = re.sub(rf'(?:địa\s+chỉ|đ/c|đc|ở|tại)[\s:]+{re.escape(address)}', ' ', clean_rem, flags=re.I)
        clean_rem = clean_rem.replace(address, ' ')

    # Làm sạch các từ thừa không thuộc về tên hay địa chỉ
    garbage_kws = [
        r'\bbán\s+(?:từ\s+)?cho\b', r'\bbán\s+từ\b', r'\bbán\b', r'\bxuất\s+cho\b', r'\bxuất\b',
        r'\bcho\s+(?:anh|chị|em|bạn|bác|cô|chú)\b', r'\b(?:anh|chị|em|bạn|bác|cô|chú)\b',
        r'\bđôi\s+giày\b', r'\bđôi\b', r'\bgiày\b',
        r'\bqua\b', r'\btại\b', r'\bở\b', r'\bkhách\b', r'\btên\b', r'\bvà\b', r'\bvới\b',
        r'\blấy\b', r'\blay\b', r'\btừ\b'
    ]
    for g in garbage_kws:
        clean_rem = re.sub(g, " ", clean_rem, flags=re.I)

    parts = [p.strip() for p in re.split(r'[,;\n\-]+', clean_rem) if p.strip()]

    name_candidates = []
    address_parts = []

    for part in parts:
        part_clean = part.strip(" ,.-:")
        if not part_clean:
            continue

        part_lower = part_clean.lower()

        # Kiểm tra xem phần này có chứa đặc điểm của địa chỉ không
        has_address_marker = (
            any(kw in part_lower for kw in ADDRESS_KEYWORDS) or
            bool(re.search(r'\d+\s*[/|\-]\s*\d+', part_clean)) or
            bool(re.search(r'\b(số|ngõ|hẻm|đường|phường|quận|tp|tỉnh)\b', part_lower)) or
            bool(re.search(r'\d+', part_clean) and len(part_clean) > 8)
        )

        if has_address_marker:
            address_parts.append(part_clean)
        else:
            words = part_clean.split()
            if 1 <= len(words) <= 5 and not re.search(r'\d', part_clean):
                name_candidates.append(part_clean)
            else:
                address_parts.append(part_clean)

    if not name and name_candidates:
        name = name_candidates[0].title()
        # Những ứng viên tên còn lại chính là thuộc về địa chỉ
        for extra in name_candidates[1:]:
            address_parts.append(extra)
    elif name and name_candidates:
        for cand in name_candidates:
            if name.lower() not in cand.lower():
                address_parts.append(cand)

    clean_address_parts = []
    for ap in address_parts:
        if name and name.lower() in ap.lower():
            continue
        ap_clean = re.sub(r'\b(lấy|lay|đôi|doi|giày|giay|qua|bán|ban|cho|anh|chị|em|bác|cô|chú)\b', '', ap, flags=re.I).strip(" ,.-:")
        if ap_clean and len(ap_clean) > 1:
            clean_address_parts.append(ap_clean)

    if not address and clean_address_parts:
        address = ", ".join(clean_address_parts)

    address = clean_addr_str(address)
    return name, address


def extract_warehouse(text: str, tx_type: str) -> Tuple[Optional[int], Optional[int], bool, str]:
    """
    Trích xuất thông tin Kho hàng và loại bỏ khỏi chuỗi để tránh lẫn vào Tên / Địa chỉ.
    Trả về: (source_wh, target_wh, is_explicit, remaining_text)
    - is_explicit: True nếu người dùng có gõ rõ từ khóa kho (kho tổng, cửa hàng, kho 1, kho 2...).
    """
    remaining = text
    is_explicit = False
    source_wh = None
    target_wh = None

    if tx_type == "TRANSFER":
        # Mẫu 1: Từ cửa hàng về kho tổng / Từ kho 2 sang kho 1
        m_t1 = re.search(r'\btừ\s+(?:kho\s+)?(?:cửa\s*hàng|cua\s*hang|showroom|2)\s+(?:về|sang|đến|qua)\s+(?:kho\s+)?(?:tổng|tong|ở\s*nhà|o\s*nha|1)\b', remaining, re.I)
        if m_t1:
            source_wh = 2
            target_wh = 1
            is_explicit = True
            remaining = remaining[:m_t1.start()] + " " + remaining[m_t1.end():]
            return source_wh, target_wh, is_explicit, remaining

        # Mẫu 2: Từ kho tổng sang cửa hàng / Từ kho 1 sang kho 2
        m_t2 = re.search(r'\btừ\s+(?:kho\s+)?(?:tổng|tong|ở\s*nhà|o\s*nha|1)\s+(?:sang|về|đến|qua)\s+(?:kho\s+)?(?:cửa\s*hàng|cua\s*hang|showroom|2)\b', remaining, re.I)
        if m_t2:
            source_wh = 1
            target_wh = 2
            is_explicit = True
            remaining = remaining[:m_t2.start()] + " " + remaining[m_t2.end():]
            return source_wh, target_wh, is_explicit, remaining

        # Mặc định chuyển từ Kho 1 sang Kho 2
        source_wh = 1
        target_wh = 2
        return source_wh, target_wh, False, remaining

    # Đối với OUTBOUND hoặc INBOUND:
    # 1. Từ khóa Kho 1 (Kho Tổng / Ở Nhà)
    wh1_pattern = r'(?:\bvào|\bvao|\btại|\btai|\bở|\bo|\bvề|\bve|\bcho|\bsang)?\s*(?:kho\s*tổng|kho\s*tong|kho\s*1|ở\s*nhà|o\s*nha|kho\s*nhà|kho\s*nha)\b'
    # 2. Từ khóa Kho 2 (Cửa Hàng / Showroom)
    wh2_pattern = r'(?:\bvào|\bvao|\btại|\btai|\bở|\bo|\bvề|\bve|\bcho|\bsang)?\s*(?:kho\s*cửa\s*hàng|kho\s*cua\s*hang|cửa\s*hàng|cua\s*hang|showroom|shop|kho\s*2)\b'

    m_wh1 = re.search(wh1_pattern, remaining, re.I)
    m_wh2 = re.search(wh2_pattern, remaining, re.I)

    if m_wh1:
        is_explicit = True
        if tx_type == "OUTBOUND":
            source_wh = 1
        else:
            target_wh = 1
        remaining = re.sub(wh1_pattern, " ", remaining, flags=re.I)
    elif m_wh2:
        is_explicit = True
        if tx_type == "OUTBOUND":
            source_wh = 2
        else:
            target_wh = 2
        remaining = re.sub(wh2_pattern, " ", remaining, flags=re.I)
    else:
        # Mặc định khi không ghi rõ:
        if tx_type == "OUTBOUND":
            source_wh = 2 # Mặc định xuất bán tại Cửa hàng
        else:
            target_wh = 1 # Mặc định nhập hàng vào Kho tổng

    return source_wh, target_wh, is_explicit, remaining


def parse_exchange_request(text_clean: str, text_normalized: str, all_prods: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Nhận diện yêu cầu Khách đổi size hoặc đổi mẫu giày:
    VD:
    - khách Trần Minh Trí đổi size 43 sang 42 lấy từ kho tổng
    - Trần Minh Trí đổi size 42 lấy ở nhà
    - khách 0344117974 đổi CTD 43 sang CTD 42 ở cửa hàng
    - 0344117974 đổi sang size 42 lấy ở cửa hàng
    - khách Long Phạm đổi sang CTD 43 ở nhà
    - khách Nguyễn Tuấn đổi CTD 42 sang LTN 43 từ kho tổng
    """
    is_exchange = bool(
        re.search(r'\b(?:đổi\s*size|đổi\s*mẫu|đổi\s*sang|đổi\s*thành|đổi\s*lấy|đổi)\b', text_clean, re.I) or
        re.search(r'\b(?:doi\s*size|doi\s*mau|doi\s*sang|doi\s*thanh|doi\s*lay)\b', text_normalized)
    )
    if not is_exchange:
        return None

    # 1. Trích xuất SĐT hoặc Tên khách
    phone, _ = extract_phone(text_clean)

    doi_split = re.split(r'\b(?:đổi\s*size|đổi\s*mẫu|đổi\s*sang|đổi\s*thành|đổi\s*lấy|đổi|doi\s*size|doi\s*mau|doi\s*sang|doi\s*thanh|doi\s*lay|doi)\b', text_clean, flags=re.I)
    before_doi = doi_split[0].strip() if len(doi_split) > 1 else ""
    after_doi = doi_split[1].strip() if len(doi_split) > 1 else text_clean

    customer_name = None
    cust_search = phone
    if not cust_search and before_doi:
        cand_name = re.sub(r'^(?:khách\s*hàng|khách|khach)\s*', '', before_doi, flags=re.I).strip(" ,.-:")
        if cand_name and len(cand_name) >= 2:
            customer_name = cand_name.title()
            cust_search = customer_name

    order = None
    if cust_search:
        order = database.find_customer_order(cust_search)

    # 2. Xác định kho lấy hàng mới
    target_wh = None
    if any(k in text_normalized for k in ["kho tong", "o nha", "kho 1", "tong"]):
        target_wh = 1
    elif any(k in text_normalized for k in ["cua hang", "showroom", "kho 2"]):
        target_wh = 2

    if not target_wh:
        target_wh = order["source_warehouse_id"] if order else 1

    # 3. Phân tích mã giày và size cũ / mới
    prod_codes = set(p['code'].upper() for p in all_prods)
    prod_map = {p['code'].upper(): p for p in all_prods}
    code_pat = r'\b(' + '|'.join(re.escape(c) for c in prod_codes) + r')\b'

    codes_found = [x.upper() for x in re.findall(code_pat, after_doi, flags=re.I)]
    sizes_found = [int(x) for x in re.findall(r'\b(3[8-9]|4[0-7])\b', after_doi)]

    if len(sizes_found) >= 2:
        old_size, new_size = sizes_found[0], sizes_found[1]
    elif len(sizes_found) == 1:
        new_size = sizes_found[0]
        old_size = order["size"] if order else None
    else:
        new_size = None
        old_size = order["size"] if order else None

    if len(codes_found) >= 2:
        old_code, new_code = codes_found[0], codes_found[1]
    elif len(codes_found) == 1:
        new_code = codes_found[0]
        old_code = order["product_code"] if order else new_code
    else:
        old_code = order["product_code"] if order else None
        new_code = old_code

    wh_names = {1: "Kho 1 (Kho Tổng - Ở Nhà)", 2: "Kho 2 (Cửa Hàng / Showroom)"}
    new_wh_name = wh_names.get(target_wh, f"Kho {target_wh}")
    old_wh_name = wh_names.get(order["source_warehouse_id"], f"Kho {order['source_warehouse_id']}") if order else "Kho xuất cũ"

    # 4. Kiểm tra tồn kho của đôi mới
    new_prod = prod_map.get(new_code) if new_code else None
    new_stock = 0
    new_variant_id = None
    if new_prod and new_size:
        v_info = find_variant_with_stock(new_prod['id'], new_size)
        if v_info:
            new_variant_id = v_info["variant_id"]
            new_stock = v_info["stock_wh1"] if target_wh == 1 else v_info["stock_wh2"]

    is_enough = (new_stock >= 1)

    missing_fields = []
    if not cust_search:
        missing_fields.append("Tên hoặc SĐT khách hàng cần đổi")
    elif not order:
        missing_fields.append(f"Không tìm thấy đơn xuất hàng của khách '{cust_search}'")
    if not new_code:
        missing_fields.append("Mã giày mới")
    if not new_size:
        missing_fields.append("Size giày mới cần đổi sang")

    cust_disp = order["partner_name"] if order else (customer_name or "Khách hàng")
    if " - " in cust_disp:
        cust_disp = cust_disp.split(" - ")[0].strip()

    return {
        "type": "EXCHANGE",
        "raw_text": text_clean,
        "partner_name": cust_disp,
        "phone": order["customer_phone"] if order else phone,
        "address": order["customer_address"] if order else None,
        "platform": order["platform"] if order else "Khác",
        "order_id": order["transaction_id"] if order else None,
        "order_code": order["transaction_code"] if order else None,
        "item_id": order["item_id"] if order else None,
        "old_variant_id": order["variant_id"] if order else None,
        "old_product_id": order["product_id"] if order else None,
        "old_product_code": old_code,
        "old_product_name": order["product_name"] if order else None,
        "old_size": old_size,
        "old_warehouse_id": order["source_warehouse_id"] if order else 1,
        "old_warehouse_name": old_wh_name,
        "new_product_id": new_prod['id'] if new_prod else None,
        "new_product_code": new_code,
        "new_product_name": new_prod['name'] if new_prod else None,
        "new_size": new_size,
        "new_warehouse_id": target_wh,
        "new_warehouse_name": new_wh_name,
        "new_stock": new_stock,
        "is_enough": is_enough,
        "unit_price": new_prod['retail_price'] if new_prod else 0,
        "total_amount": 0,
        "total_quantity": 1,
        "missing_fields": missing_fields,
        "notes": f"Đổi hàng: {old_code} sz {old_size} ({old_wh_name}) ➔ {new_code} sz {new_size} ({new_wh_name})"
    }


def parse_adjustment_request(text_clean: str, text_normalized: str, all_prods: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Nhận diện yêu cầu Bớt hoặc Thêm số lượng tồn kho nhanh:
    VD:
    - kho tổng bớt 2 đôi WTD 43
    - kho tổng thêm 2 đôi WTD 43
    - cửa hàng bớt 1 đôi CTD 41
    - ở nhà thêm 3 đôi OGD 40
    - bớt 2 đôi WTD 43 ở kho tổng
    - kho 1 giảm 2 đôi WTD 43
    - kho 2 tăng 1 đôi CTD 40
    - thêm 2 đôi WTD 43 vào cửa hàng
    - trừ 1 đôi OXD 41 ở kho 1
    """
    # Nhận diện hành động tăng / giảm tồn kho
    m_dec = re.search(r'\b(?:bớt|giảm|trừ|bỏ|hỏng|bot|giam|tru|bo|hong)\b', text_clean, re.I)
    m_inc = re.search(r'\b(?:thêm|tăng|cộng|bù|dư|them|tang|cong|bu|du)\b', text_clean, re.I)

    if not m_dec and not m_inc:
        return None

    # Loại trừ nếu là giao dịch bán cho khách (có giá tiền, sđt, từ khóa bán)
    if re.search(r'\b(?:ban cho|bán cho|xuat cho|xuất cho|giao cho|khach|khách)\b', text_clean, re.I):
        return None
    if re.search(r'\b0[35789]\d{8}\b', text_clean):
        return None
    if re.search(r'\b(?:đổi\s*size|đổi\s*mẫu|đổi\s*sang|đổi)\b', text_clean, re.I):
        return None
    if re.search(r'\b\d+\s*(?:k|tr|triệu|nghìn|vnd|đ)\b', text_clean, re.I):
        return None

    is_decrease = bool(m_dec)
    action_label = "Bớt" if is_decrease else "Thêm"
    action_type = "DECREASE" if is_decrease else "INCREASE"

    m_act = re.search(r'\b(?:bớt|giảm|trừ|bỏ|hỏng|thêm|tăng|cộng|bù|dư|bot|giam|tru|bo|hong|them|tang|cong|bu|du)\s*(\d+)\s*(?:đôi|doi|cặp|cap|chiếc|chiec)?\b', text_clean, re.I)
    if m_act and m_act.group(1):
        qty = int(m_act.group(1))
    else:
        m_q2 = re.search(r'\b(\d+)\s*(?:đôi|doi|cặp|cap|chiếc|chiec)\b', text_clean, re.I)
        qty = int(m_q2.group(1)) if m_q2 else 1

    delta = -qty if is_decrease else qty

    wh = None
    if any(re.search(rf'\b{re.escape(k)}\b', text_normalized) for k in ["kho tong", "o nha", "kho 1", "tong"]):
        wh = 1
    elif any(re.search(rf'\b{re.escape(k)}\b', text_normalized) for k in ["cua hang", "showroom", "kho 2"]):
        wh = 2

    wh_names = {1: "Kho 1 (Kho Tổng - Ở Nhà)", 2: "Kho 2 (Cửa Hàng / Showroom)"}

    prod_codes = set(p['code'].upper() for p in all_prods)
    prod_map = {p['code'].upper(): p for p in all_prods}
    code_pat = r'\b(' + '|'.join(re.escape(c) for c in prod_codes) + r')\b'

    m_code = re.search(code_pat, text_clean, flags=re.I)
    code = m_code.group(1).upper() if m_code else None
    matched_prod = prod_map.get(code) if code else None

    sizes_found = [int(x) for x in re.findall(r'\b(3[8-9]|4[0-7])\b', text_clean)]
    sz = sizes_found[-1] if sizes_found else None

    missing_fields = []
    if not wh:
        missing_fields.append("Kho cần điều chỉnh ('kho tổng' hoặc 'cửa hàng')")
    if not matched_prod:
        missing_fields.append("Mã mẫu giày")
    if not sz:
        missing_fields.append("Size giày (38-47)")

    current_stock = 0
    new_stock = 0
    variant_id = None
    is_enough = True

    if wh and matched_prod and sz:
        v_info = find_variant_with_stock(matched_prod['id'], sz)
        if v_info:
            variant_id = v_info["variant_id"]
            current_stock = v_info["stock_wh1"] if wh == 1 else v_info["stock_wh2"]
            new_stock = current_stock + delta
            if new_stock < 0:
                is_enough = False
        else:
            missing_fields.append(f"Không tìm thấy biến thể size {sz} trong hệ thống")

    wh_name = wh_names.get(wh, "Chưa chọn kho") if wh else "Chưa chọn kho"

    return {
        "type": "ADJUSTMENT",
        "raw_text": text_clean,
        "action": action_type,
        "action_label": action_label,
        "delta": delta,
        "quantity": qty,
        "total_quantity": qty,
        "warehouse_id": wh,
        "warehouse_name": wh_name,
        "product_id": matched_prod['id'] if matched_prod else None,
        "product_code": code,
        "product_name": matched_prod['name'] if matched_prod else None,
        "size": sz,
        "variant_id": variant_id,
        "current_stock": current_stock,
        "new_stock": new_stock,
        "is_enough": is_enough,
        "missing_fields": missing_fields,
        "total_amount": 0,
        "notes": f"Cân đối tồn kho: {action_label} {qty} đôi {code} size {sz} tại {wh_name} (Tồn cũ: {current_stock} ➔ Tồn mới: {new_stock})"
    }


def parse_cancel_request(text_clean: str, text_normalized: str) -> Optional[Dict[str, Any]]:
    """
    Nhận diện yêu cầu HỦY ĐƠN HÀNG:
    VD:
    - khách A hủy đơn
    - 0344117974 hủy đơn
    - hủy đơn khách Trần Minh Trí
    - hủy đơn 0344117974
    - hủy đơn PX-0144
    - hủy phiếu PX-0144
    """
    is_cancel = bool(
        re.search(r'\b(?:hủy\s*đơn\s*hàng|hủy\s*đơn|hủy\s*phiếu\s*xuất|hủy\s*phiếu|hủy\s*order)\b', text_clean, re.I) or
        re.search(r'\b(?:huy\s*don\s*hang|huy\s*don|huy\s*phieu\s*xuat|huy\s*phieu)\b', text_normalized) or
        (re.search(r'\b(?:hủy|huy)\b', text_normalized) and re.search(r'\b(?:đơn|phiếu|don|phieu|px-[\w\-]+)\b', text_clean, re.I))
    )
    if not is_cancel:
        return None

    # Không nhận nhầm nếu có từ khóa đổi size
    if re.search(r'\b(?:đổi\s*size|đổi\s*mẫu|doi\s*size|doi\s*mau)\b', text_clean, re.I):
        return None

    # 1. Trích xuất mã phiếu PX-...
    m_code = re.search(r'\b(P[XNC]-[\w\-]+)\b', text_clean, re.I)
    search_term = None
    if m_code:
        search_term = m_code.group(1).upper()

    # 2. SĐT
    if not search_term:
        phone, _ = extract_phone(text_clean)
        if phone:
            search_term = phone

    # 3. Tên khách hàng từ chuỗi
    if not search_term:
        parts = re.split(r'\b(?:hủy\s*đơn\s*hàng|hủy\s*đơn|hủy\s*phiếu\s*xuất|hủy\s*phiếu|hủy|huy\s*don|huy\s*phieu|huy)\b', text_clean, flags=re.I)
        cand_str = ""
        if len(parts) > 1:
            if parts[0].strip():
                cand_str = parts[0].strip()
            else:
                cand_str = parts[1].strip()
        else:
            cand_str = text_clean

        cand_str = re.sub(r'^(?:của\s+khách\s+hàng|của\s+khách|của\s+anh|của\s+chị|của\s+em|của|khách\s+hàng|khách|anh|chị|em|bạn)\s+', '', cand_str, flags=re.I).strip(" ,.-:")
        cand_str = re.sub(r'\s+(?:ạ|nhé|nha|với|nhá|giúp)$', '', cand_str, flags=re.I).strip(" ,.-:")
        if cand_str and len(cand_str) >= 2:
            search_term = cand_str.title()

    order = None
    if search_term:
        order = database.find_order_for_cancellation(search_term)

    missing_fields = []
    if not search_term:
        missing_fields.append("Mã phiếu (PX-...) hoặc Tên/SĐT khách cần hủy đơn")
    elif not order:
        missing_fields.append(f"Không tìm thấy đơn hàng xuất bán phù hợp với '{search_term}'")

    is_already_cancelled = False
    if order and order.get("status") == "CANCELLED":
        is_already_cancelled = True

    items = order.get("items", []) if order else []
    items_summary = ", ".join([f"{it['product_code']} sz {it['size']} ({it['quantity']} đôi)" for it in items])
    total_qty = order.get("total_quantity", 0) if order else 0
    total_amount = order.get("total_amount", 0) if order else 0
    wh_name = order.get("warehouse_name") if order else "Kho xuất"
    cust_disp = order.get("partner_name", "") if order else (search_term or "Khách hàng")
    if " - " in cust_disp:
        cust_disp = cust_disp.split(" - ")[0].strip()

    notes_action = f"Hủy phiếu {order.get('code', '')}: Hoàn trả {total_qty} đôi ({items_summary}) vào {wh_name}" if order else ""

    return {
        "type": "CANCEL",
        "raw_text": text_clean,
        "search_term": search_term,
        "transaction_id": order["id"] if order else None,
        "transaction_code": order["code"] if order else None,
        "status": order.get("status") if order else None,
        "is_already_cancelled": is_already_cancelled,
        "partner_name": cust_disp,
        "phone": order.get("customer_phone") if order else None,
        "address": order.get("customer_address") if order else None,
        "platform": order.get("platform", "Khác") if order else "Khác",
        "warehouse_id": order.get("source_warehouse_id") if order else None,
        "warehouse_name": wh_name,
        "items": items,
        "total_quantity": total_qty,
        "total_amount": total_amount,
        "missing_fields": missing_fields,
        "notes": notes_action
    }


def parse_natural_language(text: str) -> Dict[str, Any]:
    """
    Phân tích toàn năng văn bản tự nhiên:
    Hỗ trợ OUTBOUND (xuất bán), INBOUND (nhập kho), TRANSFER (chuyển kho),
    EXCHANGE (khách đổi size/đổi mẫu), ADJUSTMENT (cân đối / thêm bớt tồn kho),
    CANCEL (hủy đơn hàng).
    """
    text_clean = text.strip()
    if not text_clean:
        return {"error": "Vui lòng nhập nội dung giao dịch."}

    text_normalized = normalize_vietnamese(text_clean)
    all_prods = get_all_products()

    # 0. Kiểm tra yêu cầu HỦY ĐƠN HÀNG (CANCEL)
    cancel_parsed = parse_cancel_request(text_clean, text_normalized)
    if cancel_parsed:
        return cancel_parsed

    # 0.1 Kiểm tra yêu cầu CÂN ĐỐI / THÊM / BỚT TỒN KHO NHANH (ADJUSTMENT)
    adj_parsed = parse_adjustment_request(text_clean, text_normalized, all_prods)
    if adj_parsed:
        return adj_parsed

    # 0.2 Kiểm tra yêu cầu KHÁCH ĐỔI SIZE / ĐỔI MẪU (EXCHANGE)
    ex_parsed = parse_exchange_request(text_clean, text_normalized, all_prods)
    if ex_parsed:
        return ex_parsed

    # 1. Xác định Loại giao dịch
    is_transfer = any(kw in text_normalized for kw in [
        "chuyen kho", "chuyển kho", "chuyen tu", "chuyển từ", "dieu chuyen", "điều chuyển", "chuyen", "chuyển"
    ]) and any(kw in text_normalized for kw in ["sang", "ve", "về", "den", "đến", "kho"])

    has_inbound_kws = any(kw in text_normalized for kw in [
        "nhap kho", "nhập kho", "nhap vao", "nhập vào", "nhap hang", "nhập hàng",
        "nhap tu", "nhập từ", "mua vao", "mua vào", "nhap", "nhập",
        "nhan hang", "nhận hàng", "nhan vao", "nhận vào"
    ])

    has_into_warehouse = any(kw in text_normalized for kw in [
        "vao cua hang", "vào cửa hàng", "vao kho", "vào kho", "ve kho", "về kho",
        "nhap cua hang", "nhập cửa hàng"
    ])

    if is_transfer:
        tx_type = "TRANSFER"
    elif has_inbound_kws:
        tx_type = "INBOUND"
    elif has_into_warehouse and not any(kw in text_normalized for kw in [
        "ban cho", "bán cho", "xuat cho", "xuất cho", "giao cho", "khach", "khách", "sdt", "phone"
    ]):
        tx_type = "INBOUND"
    else:
        tx_type = "OUTBOUND"

    # 2. Nền tảng bán hàng
    platform = extract_platform(text_clean)

    # 3. Bóc tách số điện thoại
    phone, text_after_phone = extract_phone(text_clean)

    # 4. Bóc tách sản phẩm & danh sách size giày + số lượng (hỗ trợ nhiều size)
    all_prods = get_all_products()
    matched_prod, parsed_items, text_after_prod = extract_product_and_items(text_after_phone, all_prods)

    # 5. Bóc tách giá tiền (với quy tắc 3-4 chữ số tự nhân 1000)
    price, text_after_price = extract_price(text_after_prod)

    # Loại bỏ từ khóa nền tảng ra khỏi chuỗi còn lại
    remaining_clean = text_after_price
    for _, patterns in PLATFORM_KEYWORDS:
        for p in patterns:
            remaining_clean = re.sub(p, " ", remaining_clean, flags=re.I)

    # 6. Bóc tách Kho hàng
    source_wh, target_wh, is_explicit_wh, text_after_wh = extract_warehouse(remaining_clean, tx_type)

    # 7. Bóc tách Tên khách hàng & Địa chỉ từ chuỗi đã bóc sạch kho, giá, size, sđt
    name, address = extract_name_and_address(text_clean, text_after_wh, tx_type)

    # 7.1 Tự động lấy thông tin khách cũ (Địa chỉ, SĐT, Tên, Nền tảng) nếu còn thiếu
    is_autofilled = False
    autofill_fields = []
    if tx_type == "OUTBOUND" and (phone or (name and len(name) >= 2)):
        cust_profile = database.find_customer_profile(phone=phone, name=name)
        if cust_profile:
            if not phone and cust_profile.get("phone"):
                phone = cust_profile["phone"]
                is_autofilled = True
                autofill_fields.append("SĐT")
            if not name and cust_profile.get("name"):
                name = cust_profile["name"]
                is_autofilled = True
                autofill_fields.append("Tên")
            if not address and cust_profile.get("address"):
                address = cust_profile["address"]
                is_autofilled = True
                autofill_fields.append("Địa chỉ")
            if (not platform or platform == "Khác") and cust_profile.get("platform") and cust_profile["platform"] != "Khác":
                platform = cust_profile["platform"]
                is_autofilled = True
                autofill_fields.append("Nền tảng")

    # Đơn giá
    if tx_type == "TRANSFER":
        final_price = 0
    elif price is not None:
        final_price = price
    else:
        if matched_prod:
            final_price = matched_prod['cost_price'] if tx_type == "INBOUND" else matched_prod['retail_price']
        else:
            final_price = 0

    # 8. Xây dựng danh sách items_info và kiểm tra tồn kho từng biến thể
    items_info = []
    total_qty = 0
    total_amt = 0
    all_available = True

    if matched_prod and parsed_items:
        for it in parsed_items:
            sz = it["size"]
            qty = it["quantity"]
            v_info = find_variant_with_stock(matched_prod['id'], sz)
            unit_price_item = 0 if tx_type == "TRANSFER" else final_price
            if v_info:
                stk_wh1 = v_info['stock_wh1']
                stk_wh2 = v_info['stock_wh2']
                if tx_type in ["OUTBOUND", "TRANSFER"]:
                    # Nếu chưa chỉ định kho cụ thể và kho 2 không đủ nhưng kho 1 đủ
                    if not is_explicit_wh and source_wh == 2 and stk_wh2 < qty and stk_wh1 >= qty:
                        source_wh = 1
                    avail = stk_wh1 if source_wh == 1 else stk_wh2
                else:
                    avail = stk_wh1 if target_wh == 1 else stk_wh2

                is_ok = (tx_type not in ["OUTBOUND", "TRANSFER"]) or (avail >= qty)
                if not is_ok:
                    all_available = False

                items_info.append({
                    "variant_id": v_info["variant_id"],
                    "size": sz,
                    "quantity": qty,
                    "unit_price": unit_price_item,
                    "amount": qty * unit_price_item,
                    "stock_wh1": stk_wh1,
                    "stock_wh2": stk_wh2,
                    "available_stock": avail,
                    "is_available": is_ok,
                    "barcode": v_info["barcode"]
                })
            else:
                all_available = False
                items_info.append({
                    "variant_id": None,
                    "size": sz,
                    "quantity": qty,
                    "unit_price": unit_price_item,
                    "amount": qty * unit_price_item,
                    "stock_wh1": 0,
                    "stock_wh2": 0,
                    "available_stock": 0,
                    "is_available": False,
                    "barcode": None
                })
            total_qty += qty
            if tx_type != "TRANSFER":
                total_amt += qty * final_price

    # 9. Tự động tính số lần mua của khách hàng (Lần 1, Lần 2, Lần 3...)
    purchase_count = 1
    if tx_type == "OUTBOUND":
        purchase_count = database.get_customer_purchase_count(phone=phone, name=name)

    # Tên kho hiển thị
    wh_names = {
        1: "Kho 1 (Kho Tổng - Ở Nhà)",
        2: "Kho 2 (Cửa Hàng / Showroom)"
    }
    source_wh_name = wh_names.get(source_wh, "Kho 2 (Cửa Hàng)") if source_wh else None
    target_wh_name = wh_names.get(target_wh, "Kho 1 (Kho Tổng)") if target_wh else None

    if tx_type == "TRANSFER":
        warehouse_name_display = f"{source_wh_name} ➔ {target_wh_name}"
    elif tx_type == "INBOUND":
        warehouse_name_display = target_wh_name
    else:
        warehouse_name_display = source_wh_name

    # Ghi chú tổng hợp
    notes_parts = []
    if name:
        notes_parts.append(f"Khách/Đơn vị: {name}")
    if phone:
        notes_parts.append(f"SĐT: {phone}")
    if address:
        notes_parts.append(f"Đ/c: {address}")
    if platform and platform != "Khác":
        notes_parts.append(f"Nền tảng: {platform}")
    if tx_type == "OUTBOUND":
        notes_parts.append(f"Lần mua: {purchase_count}")
    notes = " | ".join(notes_parts) if notes_parts else "Nhập liệu toàn năng"

    # Kiểm tra trường còn thiếu
    missing_fields = []
    if not matched_prod:
        missing_fields.append("Mã giày")
    if not items_info:
        missing_fields.append("Size giày")
    if tx_type == "OUTBOUND" and not name and not phone:
        missing_fields.append("Tên hoặc SĐT khách hàng")

    # Các thông tin tương thích ngược với 1 size
    first_item = items_info[0] if items_info else None
    primary_size = first_item["size"] if first_item else None
    primary_variant_id = first_item["variant_id"] if first_item else None
    primary_stock_wh1 = first_item["stock_wh1"] if first_item else 0
    primary_stock_wh2 = first_item["stock_wh2"] if first_item else 0
    primary_available = first_item["available_stock"] if first_item else 0

    return {
        "raw_text": text_clean,
        "type": tx_type,
        "partner_name": name,
        "phone": phone,
        "address": address,
        "platform": platform,
        "purchase_count": purchase_count,
        "product_id": matched_prod['id'] if matched_prod else None,
        "product_code": matched_prod['code'] if matched_prod else None,
        "product_name": matched_prod['name'] if matched_prod else None,
        "items": items_info,
        "size": primary_size,
        "quantity": total_qty if total_qty > 0 else 1,
        "total_quantity": total_qty,
        "unit_price": final_price,
        "total_amount": total_amt,
        "source_warehouse_id": source_wh,
        "source_warehouse_name": source_wh_name,
        "target_warehouse_id": target_wh,
        "target_warehouse_name": target_wh_name,
        # Giữ tương thích ngược với warehouse_id
        "warehouse_id": source_wh if tx_type in ["OUTBOUND", "TRANSFER"] else target_wh,
        "warehouse_name": warehouse_name_display,
        "stock_wh1": primary_stock_wh1,
        "stock_wh2": primary_stock_wh2,
        "available_stock": primary_available,
        "all_available": all_available,
        "is_explicit_warehouse": is_explicit_wh,
        "variant_id": primary_variant_id,
        "notes": notes,
        "missing_fields": missing_fields,
        "is_autofilled": is_autofilled,
        "autofill_fields": autofill_fields
    }


def parse_and_create_transaction(text: str) -> Dict[str, Any]:
    """Phân tích văn bản tự nhiên và thực hiện tạo giao dịch vào DB."""
    parsed = parse_natural_language(text)

    if parsed.get("error"):
        return {"success": False, "error": parsed["error"], "parsed": parsed}

    if parsed.get("missing_fields"):
        return {
            "success": False,
            "error": f"Chưa đủ thông tin để tạo phiếu: Thiếu {', '.join(parsed['missing_fields'])}",
            "parsed": parsed
        }

    # 0. Nghiệp vụ HỦY ĐƠN HÀNG (CANCEL)
    if parsed.get("type") == "CANCEL":
        if parsed.get("is_already_cancelled"):
            return {
                "success": False,
                "error": f"Đơn hàng {parsed['transaction_code']} của khách {parsed['partner_name']} đã bị hủy trước đó.",
                "parsed": parsed
            }
        try:
            res = database.cancel_transaction(parsed["transaction_id"])
            items_str = ", ".join([f"{it['product_code']} sz {it['size']} ({it['quantity']} đôi)" for it in parsed.get("items", [])])
            msg = f"Đã HỦY ĐƠN {parsed['transaction_code']} của khách {parsed['partner_name']} thành công. Toàn bộ {parsed['total_quantity']} đôi ({items_str}) đã được hoàn trả lại vào {parsed['warehouse_name']}."
            return {
                "success": True,
                "message": msg,
                "transaction": res,
                "parsed": parsed
            }
        except Exception as e:
            return {"success": False, "error": f"Lỗi khi hủy đơn hàng: {str(e)}", "parsed": parsed}

    # 1. Nghiệp vụ ĐỔI SIZE / ĐỔI MẪU CHO KHÁCH (EXCHANGE)
    if parsed.get("type") == "EXCHANGE":
        if not parsed.get("is_enough"):
            return {
                "success": False,
                "error": f"{parsed['new_warehouse_name']} hiện không đủ hàng (tồn: {parsed['new_stock']}) để đổi cho khách.",
                "parsed": parsed
            }
        try:
            res = database.execute_exchange_transaction(
                transaction_id=parsed["order_id"],
                item_id=parsed["item_id"],
                old_variant_id=parsed["old_variant_id"],
                old_warehouse_id=parsed["old_warehouse_id"],
                new_product_id=parsed["new_product_id"],
                new_size=parsed["new_size"],
                new_warehouse_id=parsed["new_warehouse_id"],
                new_unit_price=parsed.get("unit_price"),
                exchange_note=parsed.get("notes")
            )
            msg = f"Đã thực hiện ĐỔI HÀNG thành công cho khách {parsed['partner_name']}: {parsed['old_product_code']} sz {parsed['old_size']} ➔ {parsed['new_product_code']} sz {parsed['new_size']} (lấy từ {parsed['new_warehouse_name']}). Đơn hàng {parsed['order_code']} và ma trận kho đã được cập nhật tự động."
            return {
                "success": True,
                "message": msg,
                "transaction": res,
                "parsed": parsed
            }
        except Exception as e:
            return {"success": False, "error": f"Lỗi khi thực hiện đổi hàng: {str(e)}", "parsed": parsed}

    # 2. Nghiệp vụ CÂN ĐỐI / BỚT / THÊM TỒN KHO NHANH (ADJUSTMENT)
    if parsed.get("type") == "ADJUSTMENT":
        if not parsed.get("is_enough"):
            return {
                "success": False,
                "error": f"{parsed['warehouse_name']} hiện có {parsed['current_stock']} đôi, không thể bớt {parsed['quantity']} đôi (tồn kho không thể âm).",
                "parsed": parsed
            }
        try:
            res = database.execute_stock_adjustment(
                warehouse_id=parsed["warehouse_id"],
                product_id=parsed["product_id"],
                size=parsed["size"],
                delta=parsed["delta"],
                reason=parsed.get("notes")
            )
            msg = f"Đã cập nhật tồn kho thành công tại {parsed['warehouse_name']}: {parsed['action_label']} {parsed['quantity']} đôi {parsed['product_code']} size {parsed['size']}. Tồn mới: {res['new_stock']} đôi."
            return {
                "success": True,
                "message": msg,
                "transaction": res,
                "parsed": parsed
            }
        except Exception as e:
            return {"success": False, "error": f"Lỗi khi cân đối tồn kho: {str(e)}", "parsed": parsed}

    items = parsed.get("items", [])
    if not items:
        return {
            "success": False,
            "error": "Không có sản phẩm/size hợp lệ trong nội dung.",
            "parsed": parsed
        }

    # Kiểm tra biến thể và tồn kho đối với OUTBOUND và TRANSFER
    for it in items:
        if not it.get("variant_id"):
            return {
                "success": False,
                "error": f"Không tìm thấy biến thể size {it['size']} của mã {parsed['product_code']} trong hệ thống.",
                "parsed": parsed
            }

        if parsed["type"] in ["OUTBOUND", "TRANSFER"]:
            if it["available_stock"] < it["quantity"]:
                wh_name = parsed["source_warehouse_name"] or parsed["warehouse_name"]
                return {
                    "success": False,
                    "error": f"{wh_name} chỉ còn {it['available_stock']} đôi mã {parsed['product_code']} size {it['size']}, không đủ xuất/chuyển {it['quantity']} đôi.",
                    "parsed": parsed
                }

    partner = parsed["partner_name"] or ("Nhà cung cấp / Xưởng sản xuất" if parsed["type"] == "INBOUND" else "Khách lẻ")
    if parsed["phone"]:
        partner = f"{partner} - {parsed['phone']}"

    tx_items = [{
        "variant_id": it["variant_id"],
        "size": it["size"],
        "quantity": it["quantity"],
        "unit_price": it["unit_price"]
    } for it in items]

    tx_data = {
        "type": parsed["type"],
        "source_warehouse_id": parsed["source_warehouse_id"],
        "target_warehouse_id": parsed["target_warehouse_id"],
        "partner_name": partner,
        "customer_phone": parsed["phone"],
        "customer_address": parsed["address"],
        "platform": parsed["platform"],
        "purchase_count": parsed["purchase_count"],
        "status": "COMPLETED",
        "notes": parsed["notes"],
        "items": tx_items
    }

    try:
        result = database.execute_stock_transaction(tx_data)
        
        type_labels = {
            "OUTBOUND": "phiếu xuất bán",
            "INBOUND": "phiếu nhập kho",
            "TRANSFER": "phiếu chuyển kho"
        }
        label = type_labels.get(parsed["type"], "phiếu giao dịch")

        customer_badge = ""
        if parsed["type"] == "OUTBOUND":
            if parsed["purchase_count"] == 1:
                customer_badge = " (Khách mới - Mua lần 1)"
            else:
                customer_badge = f" (Khách quen - Mua lần {parsed['purchase_count']})"

        wh_detail = f" từ {parsed['warehouse_name']}" if parsed["type"] == "OUTBOUND" else (f" vào {parsed['warehouse_name']}" if parsed["type"] == "INBOUND" else f" ({parsed['warehouse_name']})")
        
        items_summary = ", ".join([f"Size {it['size']} ({it['quantity']} đôi)" for it in items])
        total_qty = sum(it['quantity'] for it in items)
        
        if len(items) > 1:
            prod_summary = f"{parsed['product_code']} (Tổng {total_qty} đôi: {items_summary})"
        else:
            prod_summary = f"{parsed['product_code']} {items_summary}"

        partner_display = parsed['partner_name'] or ('Kho' if parsed['type'] == 'INBOUND' else 'Khách hàng')
        msg = f"Đã tạo thành công {label} {result['code']}{wh_detail}: {prod_summary} cho {partner_display}{customer_badge}."
        return {
            "success": True,
            "message": msg,
            "transaction": result,
            "parsed": parsed
        }
    except Exception as e:
        return {"success": False, "error": f"Lỗi khi ghi nhận phiếu: {str(e)}", "parsed": parsed}
