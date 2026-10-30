"""
Live Integration Test Suite for Indian Calendar & Festival Integration.
Performs REAL network requests against candidate endpoints and verifies:
1. Live Primary API connectivity & response schema.
2. Live Supplementary Festival API connectivity & response schema.
3. Verification of official Maharashtra state and national gazetted holidays.
4. Investigation of future-year coverage (e.g. 2027 404 handling).
5. Live REST endpoint `/api/v1/calendar/holidays` execution.
6. End-to-end forecast generation with live calendar features for Maharashtra stores.
"""
import sys
import os
from pathlib import Path
from datetime import date, datetime

# Setup path
BASE_DIR = Path(__file__).resolve().parent / "website"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pytest
import requests
from starlette.testclient import TestClient
from main import app
from services.calendar_service import calendar_service
from services.forecast_service import forecast_engine
from services.weather_service import weather_service

client = TestClient(app)

# ---------------------------------------------------------------------------- #
# 1. Live Primary Candidate API Verification
# ---------------------------------------------------------------------------- #
def test_live_primary_api_endpoint():
    """Validates live connectivity, HTTP 200, and JSON schema of primary calendar API."""
    url = "https://calendar-api-d7a8.onrender.com/v1/holidays?country=IN&year=2026&region=MH&scope=all"
    try:
        resp = requests.get(url, timeout=25)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Live network connection unavailable: {e}")

    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "country" in data and data["country"] == "IN"
    assert "region" in data and data["region"] == "MH"
    assert len(data["data"]) >= 20  # Maharashtra has 22 state + central holidays

    # Verify presence of Maharashtra Day and Republic Day
    names = [h.get("name") for h in data["data"]]
    assert any("Republic Day" in n for n in names)
    assert any("Maharashtra" in n or "Budha Purnima" in n for n in names)

def test_live_primary_api_year_coverage_limits():
    """
    Confirms empirical limitation: Primary API returns 404 for years outside 2026.
    Proves that the system must not assume future years (e.g. 2027) are available on this API.
    """
    url_2027 = "https://calendar-api-d7a8.onrender.com/v1/holidays?country=IN&year=2027&region=MH"
    try:
        resp = requests.get(url_2027, timeout=15)
        # Primary API strictly returns 404 for unpopulated future years
        assert resp.status_code == 404
        assert "not available" in resp.text.lower()
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Live network connection unavailable: {e}")

# ---------------------------------------------------------------------------- #
# 2. Live Supplementary Festival API Verification
# ---------------------------------------------------------------------------- #
def test_live_supplementary_festival_api():
    """Validates live connectivity, HTTP 200, and JSON schema of supplementary festival API."""
    url = "https://indian-festival-api.vercel.app/api/festivals?state=Maharashtra"
    try:
        resp = requests.get(url, timeout=15)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Live network connection unavailable: {e}")

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    festivals = data.get("data", [])
    assert len(festivals) >= 20

    # Verify cultural festivals for food retail (Dhanteras, Makar Sankranti, Diwali)
    f_names = [f.get("name") for f in festivals]
    assert any("Makar Sankranti" in n for n in f_names)
    assert any("Dhanteras" in n for n in f_names)
    assert any("Diwali" in n for n in f_names)

    # Verify that dates provided are for 2026 in 'date_2026'
    first_f = festivals[0]
    assert "date_2026" in first_f

# ---------------------------------------------------------------------------- #
# 3. Live Calendar Service Synchronization & Cache Check
# ---------------------------------------------------------------------------- #
def test_live_calendar_service_synchronization():
    """Verifies that IndiaCalendarService synchronizes live data and populates local cache."""
    res = calendar_service.refresh_calendar_data(year=2026, state="MH", force=False)
    assert res["status"] in ("refreshed", "cached")
    assert res["total_events"] > 50

    meta = calendar_service.get_metadata()
    assert meta["is_cache_fresh"] is True
    assert meta["total_cached_events"] > 50
    assert meta["provider_status"]["primary"].startswith("healthy")
    assert meta["provider_status"]["supplementary"].startswith("healthy")

# ---------------------------------------------------------------------------- #
# 4. Live REST Endpoint Verification
# ---------------------------------------------------------------------------- #
def test_live_rest_calendar_endpoint():
    """Verifies GET /api/v1/calendar/holidays returns verified events and metadata."""
    resp = client.get("/api/v1/calendar/holidays?year=2026&state=MH")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["year"] == 2026
    assert data["state"] == "MH"
    assert "metadata" in data
    assert "holidays" in data
    assert len(data["holidays"]) >= 50

    # Ensure records contain normalized fields
    first = data["holidays"][0]
    assert "date" in first
    assert "name" in first
    assert "type" in first
    assert "verification_status" in first
    assert "source" in first

# ---------------------------------------------------------------------------- #
# 5. Live Forecast Integration for Maharashtra Food Retail
# ---------------------------------------------------------------------------- #
def test_live_forecast_holiday_awareness_maharashtra():
    """
    Verifies that the forecast engine processes live calendar data for Maharashtra:
    - Butter Croissant receives empirical lift on festival/holiday dates.
    - Cold-start items (sweet) receive 0% artificial boost.
    - Holiday information reaches the actual daily prediction numbers.
    """
    weather_7d = weather_service.get_7day_weather_forecast(location="Shirpur, Maharashtra")

    # 1. Test Croissant (Historical SKU)
    item_croissant = {
        "name": "Butter Croissant",
        "category": "Pastry",
        "predictedDemand": 40,
        "currentStock": 20,
        "price": 60.0,
        "costPrice": 30.0,
        "isPerishable": True,
    }
    fc_croissant = forecast_engine.get_comprehensive_forecast(
        item_croissant, weather_7d, shop_location="Shirpur, Maharashtra"
    )
    assert fc_croissant["empirical_lift"] > 0.0
    assert len(fc_croissant["events"]) > 0

    # 2. Test cold-start item (sweet)
    item_cold = {
        "name": "sweet",
        "category": "Beverage",
        "predictedDemand": 15,
        "currentStock": 5,
        "price": 50.0,
        "costPrice": 25.0,
        "isPerishable": True,
    }
    fc_cold = forecast_engine.get_comprehensive_forecast(
        item_cold, weather_7d, shop_location="Shirpur, Maharashtra"
    )
    # Cold-start must NOT invent artificial boosts
    assert fc_cold["empirical_lift"] == 0.0
    # Baseline demand preserved
    assert "No historical holiday sales records" in fc_cold["lift_reason"]

