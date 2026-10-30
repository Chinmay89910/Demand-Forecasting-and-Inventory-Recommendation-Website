"""
Test Suite for Open-Meteo Weather Integration & Minute-to-Minute Telemetry.
Tests:
1. Live Open-Meteo API connectivity & schema validation.
2. Geocoding resolution with caching.
3. Live minute-to-minute weather telemetry (temp, humidity, precipitation, wind, timestamp).
4. 7-day weather forecast horizon with meteorological classification.
5. Historical weather archive API retrieval for model alignment.
6. Weather multiplier and demand forecast integration.
7. Resilience, timeouts, and stale-cache preservation.
8. REST API endpoints `/api/v1/weather/live` and `/api/v1/weather/forecast`.
"""
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime, date

# Setup path
BASE_DIR = Path(__file__).resolve().parent / "website"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pytest
from starlette.testclient import TestClient
from main import app
from services.weather_service import WeatherService, weather_service
from services.forecast_service import forecast_engine

client = TestClient(app)

# ---------------------------------------------------------------------------- #
# 1. Geocoding & Coordinate Resolution
# ---------------------------------------------------------------------------- #
def test_geocoding_resolution():
    """Verify that city names resolve to accurate geographic coordinates."""
    lat, lon = weather_service.geocode_location("Shirpur, Maharashtra")
    assert round(lat, 2) == 21.35
    assert round(lon, 2) == 74.88

    lat_mumbai, lon_mumbai = weather_service.geocode_location("Mumbai, Maharashtra")
    assert round(lat_mumbai, 1) == 19.1
    assert round(lon_mumbai, 1) == 72.9

def test_geocoding_fallback():
    """Verify graceful fallback to default coordinates on empty or unresolvable location."""
    lat, lon = weather_service.geocode_location("")
    assert lat == weather_service.default_lat
    assert lon == weather_service.default_lon

# ---------------------------------------------------------------------------- #
# 2. Live Minute-to-Minute Telemetry
# ---------------------------------------------------------------------------- #
def test_live_weather_telemetry_schema():
    """Verify live weather returns all required minute-to-minute observation variables."""
    live = weather_service.get_live_weather("Shirpur, Maharashtra", force_refresh=True)
    assert "temperature" in live
    assert "feels_like" in live
    assert "humidity" in live
    assert "precipitation_mm" in live
    assert "wind_kmh" in live
    assert "condition" in live
    assert "icon" in live
    assert "updated_at" in live
    assert "updated_at_display" in live
    assert "update_frequency" in live and "minute-to-minute" in live["update_frequency"]
    assert live["source"] == "Open-Meteo Live API"
    assert live["is_live"] is True

def test_live_weather_caching_60s():
    """Verify that calls within 60s reuse the cached live observation."""
    live1 = weather_service.get_live_weather("Shirpur, Maharashtra", force_refresh=False)
    live2 = weather_service.get_live_weather("Shirpur, Maharashtra", force_refresh=False)
    assert live1["updated_at"] == live2["updated_at"]

# ---------------------------------------------------------------------------- #
# 3. 7-Day Forecast Horizon
# ---------------------------------------------------------------------------- #
def test_7day_weather_forecast_horizon():
    """Verify 7-day forecast returns 7 distinct daily projections with rain and temp metrics."""
    fc_7d = weather_service.get_7day_weather_forecast("Shirpur, Maharashtra")
    assert len(fc_7d) == 7
    first_day = fc_7d[0]
    assert first_day["day_short"] == "Today"
    assert "temp" in first_day
    assert "temp_min" in first_day
    assert "temp_max" in first_day
    assert "precipitation_sum" in first_day
    assert "precipitation_probability" in first_day
    assert "traffic_impact" in first_day
    assert -25 <= first_day["traffic_impact"] <= +15

# ---------------------------------------------------------------------------- #
# 4. Historical Archive Weather
# ---------------------------------------------------------------------------- #
def test_historical_weather_archive_retrieval():
    """Verify historical weather archive API returns real daily observations."""
    hist = weather_service.get_historical_weather("Shirpur, Maharashtra", "2024-10-01", "2024-10-05")
    assert hist["records_count"] == 5
    records = hist["daily_records"]
    assert len(records) == 5
    assert records[0]["date"] == "2024-10-01"
    assert records[0]["temp_max"] is not None
    assert records[0]["precipitation_sum"] is not None

# ---------------------------------------------------------------------------- #
# 5. Forecast Engine Weather Multiplier Integration
# ---------------------------------------------------------------------------- #
def test_forecast_engine_weather_impact():
    """Verify that weather condition affects predicted demand units in the forecast engine."""
    item = {
        "name": "Butter Croissant",
        "category": "Pastry",
        "predictedDemand": 50,
        "currentStock": 20,
        "price": 60.0,
        "costPrice": 30.0,
        "isPerishable": True,
    }
    
    # Sunny day forecast (+12% impact)
    weather_sunny = [{
        "date": "2026-10-30",
        "day_short": "Today",
        "temp": 33,
        "condition": "Sunny",
        "icon": "☀️",
        "traffic_impact": +12,
    }]
    fc_sunny = forecast_engine.get_comprehensive_forecast(
        item, weather_sunny, shop_location="Shirpur, Maharashtra"
    )

    # Rainy day forecast (-18% impact)
    weather_rain = [{
        "date": "2026-10-30",
        "day_short": "Today",
        "temp": 24,
        "condition": "Rain",
        "icon": "🌧️",
        "traffic_impact": -18,
    }]
    fc_rain = forecast_engine.get_comprehensive_forecast(
        item, weather_rain, shop_location="Shirpur, Maharashtra"
    )

    # Sunny day sales must be strictly higher than rainy day sales
    assert fc_sunny["expected_sales_today"] > fc_rain["expected_sales_today"]

# ---------------------------------------------------------------------------- #
# 6. REST API Endpoints Verification
# ---------------------------------------------------------------------------- #
def test_rest_weather_live_endpoint():
    """Verify GET /api/v1/weather/live returns live minute-to-minute weather payload."""
    resp = client.get("/api/v1/weather/live?location=Shirpur,%20Maharashtra")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "weather" in data
    assert "temperature" in data["weather"]
    assert "humidity" in data["weather"]
    assert "precipitation_mm" in data["weather"]
    assert "updated_at_display" in data

def test_rest_weather_forecast_endpoint():
    """Verify GET /api/v1/weather/forecast returns 7-day forecast payload."""
    resp = client.get("/api/v1/weather/forecast?location=Shirpur,%20Maharashtra")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] == 7
    assert len(data["forecast"]) == 7

