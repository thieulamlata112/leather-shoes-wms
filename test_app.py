from fastapi.testclient import TestClient
import app
import database

client = TestClient(app.app)

def test_api_network_info():
    response = client.get("/api/network-info")
    assert response.status_code == 200
    data = response.json()
    assert "network_url" in data
    assert "port" in data
    print("[OK] /api/network-info:", data["network_url"])

def test_get_warehouses():
    response = client.get("/api/warehouses")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    assert any("Kho 1" in w["name"] for w in data)
    assert any("Kho 2" in w["name"] for w in data)
    print("[OK] /api/warehouses: found", len(data), "warehouses")

def test_get_products_and_variants():
    response = client.get("/api/products")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 4
    first_prod = data[0]
    assert "variants" in first_prod
    sizes = [v["size"] for v in first_prod["variants"]]
    assert 38 in sizes and 44 in sizes
    print(f"[OK] /api/products: {first_prod['code']} has sizes {sizes}")

def test_barcode_lookup():
    response = client.get("/api/barcode/lookup?code=GD-OXFORD-01-40")
    assert response.status_code == 200
    data = response.json()
    assert data["found_type"] == "variant"
    assert data["data"]["size"] == 40
    print("[OK] /api/barcode/lookup: found size 40, stock_wh1 =", data["data"]["stock_wh1"])

def test_stock_lifecycle_inbound_transfer_outbound():
    # 1. Lấy thông tin ban đầu của biến thể GD-OXFORD-01 size 40
    lookup_res = client.get("/api/barcode/lookup?code=GD-OXFORD-01-40")
    v_data = lookup_res.json()["data"]
    variant_id = v_data["id"]
    initial_wh1 = v_data["stock_wh1"]
    initial_wh2 = v_data["stock_wh2"]
    
    # 2. Nhập thêm 10 đôi vào Kho 1
    inbound_res = client.post("/api/transactions", json={
        "type": "INBOUND",
        "target_warehouse_id": 1,
        "partner_name": "Xưởng Da Giày Test",
        "notes": "Nhập thử nghiệm",
        "items": [{
            "variant_id": variant_id,
            "size": 40,
            "quantity": 10,
            "unit_price": 750000
        }]
    })
    assert inbound_res.status_code == 200
    
    # Kiểm tra tồn Kho 1 tăng thêm 10
    v_after_in = client.get("/api/barcode/lookup?code=GD-OXFORD-01-40").json()["data"]
    assert v_after_in["stock_wh1"] == initial_wh1 + 10
    print("[OK] Inbound: Kho 1 tang tu", initial_wh1, "len", v_after_in["stock_wh1"])
    
    # 3. Chuyển 4 đôi từ Kho 1 sang Kho 2
    transfer_res = client.post("/api/transactions", json={
        "type": "TRANSFER",
        "source_warehouse_id": 1,
        "target_warehouse_id": 2,
        "notes": "Chuyển bổ sung showroom",
        "items": [{
            "variant_id": variant_id,
            "size": 40,
            "quantity": 4,
            "unit_price": 750000
        }]
    })
    assert transfer_res.status_code == 200
    
    v_after_tr = client.get("/api/barcode/lookup?code=GD-OXFORD-01-40").json()["data"]
    assert v_after_tr["stock_wh1"] == initial_wh1 + 10 - 4
    assert v_after_tr["stock_wh2"] == initial_wh2 + 4
    print("[OK] Transfer: Kho 1 con", v_after_tr["stock_wh1"], ", Kho 2 co", v_after_tr["stock_wh2"])
    
    # 4. Xuất bán 2 đôi từ Kho 2
    outbound_res = client.post("/api/transactions", json={
        "type": "OUTBOUND",
        "source_warehouse_id": 2,
        "partner_name": "Khách Test V.I.P",
        "notes": "Xuất bán lẻ",
        "items": [{
            "variant_id": variant_id,
            "size": 40,
            "quantity": 2,
            "unit_price": 1450000
        }]
    })
    assert outbound_res.status_code == 200
    
    v_after_out = client.get("/api/barcode/lookup?code=GD-OXFORD-01-40").json()["data"]
    assert v_after_out["stock_wh2"] == initial_wh2 + 4 - 2
    print("[OK] Outbound: Kho 2 sau khi ban con", v_after_out["stock_wh2"])

def test_export_excel():
    response = client.get("/api/export/excel")
    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers["content-type"]
    assert len(response.content) > 1000
    print("[OK] /api/export/excel: generated valid xlsx file of size", len(response.content), "bytes")

def test_static_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "Hệ Thống Quản Lý Kho Giày Da" in response.text
    print("[OK] Static index.html served OK!")

if __name__ == "__main__":
    test_api_network_info()
    test_get_warehouses()
    test_get_products_and_variants()
    test_barcode_lookup()
    test_stock_lifecycle_inbound_transfer_outbound()
    test_export_excel()
    test_static_html()
    print("\n=== TAT CA CAC BAI KIEM THU DAU VUOT QUA THANH CONG! ===")
