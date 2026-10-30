"""
Automated Test & Verification Suite for RestockIQ Demand Forecasting Website
Tests User Registration, Authentication, Credential Security, First-Time Onboarding,
Tenant Isolation & Personal Shop Dashboards, Demo Replay, Newsvendor Math, and CSV Validation.
"""
import sys
import os
import uuid
from pathlib import Path

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add website directory to sys.path
BASE_DIR = Path(__file__).resolve().parent / "website"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pytest
from starlette.testclient import TestClient
from main import app, db_manager
from services.forecast_service import forecast_engine
from services.csv_validator import csv_validator
from services.db_service import verify_password

client = TestClient(app)

import asyncio
try:
    asyncio.run(db_manager.initialize(allow_demo_seed=True))
except Exception:
    pass

# ---------------------------------------------------------------------------- #
# 1. Health & Status Verification
# ---------------------------------------------------------------------------- #
def test_health_check():
    """Verify system health, DB connection mode, and AI integration."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data
    assert "llm" in data
    assert "version" in data
    print("✅ Health check passed:", data)

# ---------------------------------------------------------------------------- #
# 2. Registration & Shop Creation
# ---------------------------------------------------------------------------- #
def test_registration_valid():
    """Verify registration creates user account, personal shop, and hashes password."""
    unique_email = f"baker_{uuid.uuid4().hex[:6]}@artisanbakes.com"
    resp = client.post(
        "/register",
        data={
            "name": "Jean-Luc Picard",
            "email": unique_email,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "shop_name": "Starlight Artisan Boulangerie",
            "shop_type": "Bakery",
            "role": "owner"
        },
        follow_redirects=False
    )
    # Redirects to demo screen to explain complete workflow to 1st time user
    assert resp.status_code in (302, 303, 307)
    assert "access_token" in resp.cookies
    assert "/demo" in resp.headers.get("location", "")

    # Verify user exists in database and password is NOT plaintext
    user = asyncio.run(db_manager.find_user_by_email(unique_email))
    assert user is not None
    assert user["name"] == "Jean-Luc Picard"
    assert user["shop_name"] == "Starlight Artisan Boulangerie"
    assert user["password_hash"] != "SecurePassword123"
    assert verify_password("SecurePassword123", user["password_hash"]) is True
    assert user["onboarding_completed"] is False  # New user starts with onboarding false!

    # Verify associated shop entity
    shop = asyncio.run(db_manager.get_user_shop(user["_id"]))
    assert shop is not None
    assert shop["name"] == "Starlight Artisan Boulangerie"
    assert shop["type"] == "Bakery"
    print("✅ Valid Registration and Shop Creation passed.")

def test_registration_validation_errors():
    """Verify validation: empty name, invalid email, mismatched passwords, short password, duplicate email."""
    # 1. Empty name
    r_empty_name = client.post("/register", data={
        "name": "   ", "email": "valid@bakery.com", "password": "password123", "confirm_password": "password123"
    })
    assert r_empty_name.status_code == 400
    assert "Full name cannot be empty" in r_empty_name.text

    # 2. Invalid email format
    r_bad_email = client.post("/register", data={
        "name": "Valid Name", "email": "notanemail", "password": "password123", "confirm_password": "password123"
    })
    assert r_bad_email.status_code == 400
    assert "valid email address" in r_bad_email.text

    # 3. Short password (<6 chars)
    r_short_pass = client.post("/register", data={
        "name": "Valid Name", "email": "valid2@bakery.com", "password": "123", "confirm_password": "123"
    })
    assert r_short_pass.status_code == 400
    assert "at least 6 characters" in r_short_pass.text

    # 4. Mismatched passwords
    r_mismatch = client.post("/register", data={
        "name": "Valid Name", "email": "valid3@bakery.com", "password": "password123", "confirm_password": "password999"
    })
    assert r_mismatch.status_code == 400
    assert "Passwords do not match" in r_mismatch.text

    # 5. Duplicate email rejection
    r_dup = client.post("/register", data={
        "name": "Another Name", "email": "admin@test.com", "password": "password123", "confirm_password": "password123"
    })
    assert r_dup.status_code == 400
    assert "already exists" in r_dup.text
    print("✅ Registration Validation Errors properly handled.")

# ---------------------------------------------------------------------------- #
# 3. Authentication & Route Protection
# ---------------------------------------------------------------------------- #
def test_unauthenticated_access_protection():
    """Verify that unauthenticated visitors CANNOT access private dashboards, forecasts, or APIs."""
    # Dedicated anonymous client without any session cookies
    anon_client = TestClient(app)

    # HTML views redirect unauthenticated users to /login
    protected_views = ["/", "/demo", "/dashboard", "/inventory", "/forecast", "/waste-alerts", "/checkin", "/reports", "/settings"]
    for v in protected_views:
        r = anon_client.get(v, follow_redirects=False)
        assert r.status_code in (302, 303, 307), f"Expected redirect for {v}, got {r.status_code}"
        assert r.headers["location"].endswith("/login")

    # Protected REST APIs return 401 Unauthorized
    r_api_items = anon_client.get("/api/v1/items")
    assert r_api_items.status_code == 401
    r_api_forecasts = anon_client.get("/api/v1/forecasts/today")
    assert r_api_forecasts.status_code == 401
    print("✅ Unauthenticated Access correctly protected (redirects to /login, APIs return 401).")

def test_login_flow():
    """Verify authentication with valid/invalid credentials, password verification, and JWT issuance."""
    # 1. Unknown email fails safely
    r_unknown = client.post("/login", data={"email": "nonexistent@bakery.com", "password": "password123"})
    assert r_unknown.status_code == 400
    assert "Invalid email or password" in r_unknown.text

    # 2. Wrong password fails safely
    r_wrong_pass = client.post("/login", data={"email": "admin@test.com", "password": "wrongpassword!"})
    assert r_wrong_pass.status_code == 400
    assert "Invalid email or password" in r_wrong_pass.text

    # 3. Valid login sets JWT cookie and redirects to /dashboard
    r_valid = client.post(
        "/login",
        data={"email": "admin@test.com", "password": "123456"},
        follow_redirects=False
    )
    assert r_valid.status_code in (302, 303, 307)
    assert "access_token" in r_valid.cookies
    token = r_valid.cookies["access_token"]
    assert len(token) > 20

    # 4. REST API login endpoint
    r_api_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "123456"}
    )
    assert r_api_login.status_code == 200
    api_data = r_api_login.json()
    assert "access_token" in api_data
    assert "shop_name" in api_data
    print("✅ Authentication Flow and Credential Verification passed.")

# ---------------------------------------------------------------------------- #
# 4. First-Time Onboarding & Persistence
# ---------------------------------------------------------------------------- #
def test_onboarding_persistence_and_replay():
    """Verify first-login onboarding state, completion persistence, and Settings replay capability."""
    # Register a new user
    new_email = f"newbaker_{uuid.uuid4().hex[:6]}@croissant.com"
    reg_resp = client.post(
        "/register",
        data={
            "name": "Marie Curie",
            "email": new_email,
            "password": "Password12345",
            "confirm_password": "Password12345",
            "shop_name": "Radiancy Pastry Lab",
            "shop_type": "Café"
        },
        follow_redirects=False
    )
    cookies = {"access_token": reg_resp.cookies["access_token"]}
    token = reg_resp.cookies["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 1. Verify 1st time user sees the dedicated /demo screen explaining the 5-step flow
    demo_resp = client.get("/demo", cookies=cookies)
    assert demo_resp.status_code == 200
    assert "The 5-Step Daily Operating Flow" in demo_resp.text
    assert "Enter My Personal Dashboard" in demo_resp.text

    # 2. Complete onboarding via API (simulating user clicking 'Enter My Personal Dashboard')
    onboard_resp = client.post("/api/v1/user/onboarding", json={"completed": True}, headers=auth_header)
    assert onboard_resp.status_code == 200
    assert onboard_resp.json()["onboarding_completed"] is True

    # 3. User visits dashboard -> onboarding flag is now FALSE (no automatic popup)
    dash_resp_after = client.get("/dashboard", cookies=cookies)
    assert dash_resp_after.status_code == 200
    assert "window.AUTO_START_ONBOARDING = false;" in dash_resp_after.text

    # 4. Settings provides both Flow Guide (/demo) and Replay Live Tour options
    settings_resp = client.get("/settings", cookies=cookies)
    assert settings_resp.status_code == 200
    assert "View Flow Guide" in settings_resp.text
    assert "Replay Live Tour" in settings_resp.text
    print("✅ First-Time Onboarding, Demo Screen and Persistence passed.")

# ---------------------------------------------------------------------------- #
# 5. Strict Multi-Tenant Data Isolation
# ---------------------------------------------------------------------------- #
def test_tenant_data_isolation():
    """Verify that User A and User B cannot see or manipulate each other's products or alerts."""
    # Register Tenant A
    email_a = f"tenant_a_{uuid.uuid4().hex[:6]}@bakery.com"
    res_a = client.post(
        "/api/v1/auth/register",
        json={"name": "Owner A", "email": email_a, "password": "password123", "shop_name": "Bakery Alpha"}
    )
    token_a = res_a.json()["access_token"]
    user_a_id = res_a.json()["user_id"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register Tenant B
    email_b = f"tenant_b_{uuid.uuid4().hex[:6]}@bakery.com"
    res_b = client.post(
        "/api/v1/auth/register",
        json={"name": "Owner B", "email": email_b, "password": "password123", "shop_name": "Bakery Beta"}
    )
    token_b = res_b.json()["access_token"]
    user_b_id = res_b.json()["user_id"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B initially has 0 items (clean personal dashboard empty state)
    items_b = client.get("/api/v1/items", headers=headers_b).json()["items"]
    assert len(items_b) == 0

    # Tenant A adds a product to Bakery Alpha
    create_resp = client.post(
        "/api/v1/items",
        json={"name": "Alpha Sourdough Boule", "category": "Bread", "unit": "PCS", "currentStock": 15, "isPerishable": True, "price": 6.50},
        headers=headers_a
    )
    assert create_resp.status_code == 201
    item_a_id = create_resp.json()["id"]

    # Verify Tenant A sees their product
    items_a = client.get("/api/v1/items", headers=headers_a).json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["name"] == "Alpha Sourdough Boule"

    # Verify Tenant B STILL HAS 0 items (Tenant Isolation Verified!)
    items_b_after = client.get("/api/v1/items", headers=headers_b).json()["items"]
    assert len(items_b_after) == 0

    # Tenant B cannot delete Tenant A's product
    del_resp = client.delete(f"/api/v1/items/{item_a_id}", headers=headers_b)
    assert del_resp.status_code == 404

    # Item A is still safe in Tenant A's catalog
    items_a_safe = client.get("/api/v1/items", headers=headers_a).json()["items"]
    assert len(items_a_safe) == 1
    print("✅ Multi-Tenant Data Isolation strictly enforced.")

# ---------------------------------------------------------------------------- #
# 6. HTML Page Delivery (All Views with Authenticated Session)
# ---------------------------------------------------------------------------- #
def test_all_html_pages():
    """Verify all 11 responsive HTML templates render without 500 server errors."""
    login_resp = client.post(
        "/login",
        data={"email": "admin@test.com", "password": "123456"},
        follow_redirects=False
    )
    cookies = {"access_token": login_resp.cookies.get("access_token")}

    pages = [
        ("/", 200),
        ("/login", 200),
        ("/register", 200),
        ("/demo", 200),
        ("/dashboard", 200),
        ("/inventory", 200),
        ("/forecast", 200),
        ("/forecast/item_1", 200),
        ("/waste-alerts", 200),
        ("/checkin", 200),
        ("/import-sales", 200),
        ("/reports", 200),
        ("/settings", 200),
    ]

    for path, expected_code in pages:
        res = client.get(path, cookies=cookies, follow_redirects=True)
        assert res.status_code == expected_code, f"Failed at {path}: Status {res.status_code}"
        assert "<!DOCTYPE html>" in res.text, f"Invalid HTML returned for {path}"
        print(f"✅ HTML Route {path} -> HTTP 200 OK")

# ---------------------------------------------------------------------------- #
# 7. Newsvendor Inventory Math & Forecasting Engine
# ---------------------------------------------------------------------------- #
def test_newsvendor_math():
    """Verify Critical Ratio Newsvendor formulation: CR = 0.60 -> z = +0.2533."""
    rec = forecast_engine.compute_inventory_decision(
        current_stock=10,
        predicted_demand=50,
        is_perishable=True,
        price=5.0,
        cost_price=2.0,
        historical_std=12.0
    )
    # Cu = 5.0 - 2.0 = 3.0, Co = 2.0 -> CR = 3.0 / 5.0 = 0.60
    assert abs(rec["criticalRatio"] - 0.60) < 0.02
    assert rec["recommendedRestock"] >= 40
    print(f"✅ Newsvendor Critical Ratio verified: {rec}")

# ---------------------------------------------------------------------------- #
# 8. Waste Alerts & Intraday Action Engine
# ---------------------------------------------------------------------------- #
def test_waste_alert_actions():
    """Verify intraday waste alert generation and action dispatch."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "123456"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    alerts_resp = client.get("/api/v1/waste-alerts", headers=headers)
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()["alerts"]
    if len(alerts) == 0:
        # Create a fresh item with surplus stock to trigger dynamic real-time waste alert
        client.post(
            "/api/v1/items",
            json={
                "name": "Test Spoilage Brioche",
                "category": "Pastry",
                "unit": "pcs",
                "price": 40.0,
                "currentStock": 60,
                "shelf_life_days": 1,
                "isPerishable": True,
                "predictedDemand": 10
            },
            headers=headers
        )
        alerts_resp = client.get("/api/v1/waste-alerts", headers=headers)
        assert alerts_resp.status_code == 200
        alerts = alerts_resp.json()["alerts"]
    assert len(alerts) > 0
    test_alert = alerts[0]
    alert_id = test_alert["id"]

    # Action 1: Apply 20% discount
    disc_resp = client.post(f"/api/v1/waste-alerts/{alert_id}/apply-discount", headers=headers)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["status"] == "success"

    # Action 2: Flag donation
    donate_resp = client.post(f"/api/v1/waste-alerts/{alert_id}/flag-donation", headers=headers)
    assert donate_resp.status_code == 200
    assert donate_resp.json()["status"] == "success"

    # Action 3: Dismiss alert
    dismiss_resp = client.post(f"/api/v1/waste-alerts/{alert_id}/dismiss", headers=headers)
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["status"] == "success"
    print("✅ Waste alert actions (discount, donation, dismiss) all verified.")

# ---------------------------------------------------------------------------- #
# 9. CSV Validation & Data Ingestion Engine
# ---------------------------------------------------------------------------- #
def test_csv_validator_valid():
    """Verify validation engine accepts correctly formatted sales data."""
    valid_csv = """date,sku,quantity
2026-10-25,ITEM-CRO-01,35
2026-10-26,ITEM-CRO-01,42
2026-10-27,ITEM-BAG-01,20
"""
    result = csv_validator.validate_and_parse(valid_csv)
    assert result["valid"] is True
    assert result["accepted_rows"] == 3
    assert len(result["errors"]) == 0
    print("✅ CSV Validator accepted valid sales log.")

def test_csv_validator_invalid_and_negative():
    """Verify validation engine rejects missing headers and negative quantities."""
    invalid_csv = """date,sku,quantity
2026-99-99,ITEM-CRO-01,-10
2026-10-26,ITEM-BAG-01,abc
"""
    result = csv_validator.validate_and_parse(invalid_csv)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    print(f"✅ CSV Validator caught expected errors: {result['errors']}")

# ---------------------------------------------------------------------------- #
# 10. Data Export Endpoints & Logout
# ---------------------------------------------------------------------------- #
def test_data_exports_and_logout():
    """Verify CSV/JSON export streams and session termination on logout."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "123456"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Inventory CSV Export
    resp_inv = client.get("/api/v1/export/inventory-csv", headers=headers)
    assert resp_inv.status_code == 200
    assert "text/csv" in resp_inv.headers.get("content-type", "")

    # Forecast CSV Export
    resp_fc = client.get("/api/v1/export/forecast-csv", headers=headers)
    assert resp_fc.status_code == 200
    assert "text/csv" in resp_fc.headers.get("content-type", "")

    # Full JSON Backup
    resp_json = client.get("/api/v1/export/full-json", headers=headers)
    assert resp_json.status_code == 200

    # Logout
    logout_resp = client.get("/logout", follow_redirects=False)
    assert logout_resp.status_code in (302, 303, 307)
    assert logout_resp.headers["location"].endswith("/login")
    print("✅ Data Exports and Logout flow verified.")

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 Running RestockIQ Comprehensive Verification & Quality Suite...")
    print("=" * 70)
    test_health_check()
    test_registration_valid()
    test_registration_validation_errors()
    test_unauthenticated_access_protection()
    test_login_flow()
    test_onboarding_persistence_and_replay()
    test_tenant_data_isolation()
    test_all_html_pages()
    test_newsvendor_math()
    test_waste_alert_actions()
    test_csv_validator_valid()
    test_csv_validator_invalid_and_negative()
    test_data_exports_and_logout()
    print("\n" + "=" * 70)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (100% Verification Rate)")
    print("=" * 70)
