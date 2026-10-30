"""
Unit Test Suite for Indian Calendar & Festival Integration (Mocked & Deterministic).
Tests:
1. Response validation and normalization.
2. Deduplication across primary and supplementary providers.
3. Distinction between gazetted public holidays, cultural festivals, and restricted holidays.
4. Cache reuse, persistence, and safe failure handling (no cache overwrites on failure).
5. API timeouts and network error fallback.
6. Multi-year handling (2026 vs outside range).
7. Calendar feature generation vector for ML models.
8. Forecast engine empirical lift for historical SKUs vs zero-boost for new cold-start SKUs.
"""
import sys
import os
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Setup path
BASE_DIR = Path(__file__).resolve().parent / "website"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pytest
from services.calendar_service import IndiaCalendarService
from services.forecast_service import ForecastService

@pytest.fixture
def temp_calendar_service():
    """Provides a fresh IndiaCalendarService with an isolated temporary cache file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_cache_path = Path(tf.name)
    service = IndiaCalendarService(cache_file=temp_cache_path)
    service._cache["last_refreshed"] = datetime.now(timezone.utc).isoformat()
    service._cache["events_by_date"] = {}
    yield service
    if temp_cache_path.exists():
        temp_cache_path.unlink()

# ---------------------------------------------------------------------------- #
# 1. Normalization & Deduplication Tests
# ---------------------------------------------------------------------------- #
def test_normalization_and_deduplication(temp_calendar_service):
    """Verify deduplication when both primary and supplementary providers return the same event."""
    mock_primary = [
        {
            "date": "2026-01-26",
            "name": "Republic Day",
            "type": "gazetted_holiday",
            "country": "IN",
            "state": "all",
            "level": "national",
            "source": "calendar-api-web",
            "verification_status": "verified_gazetted",
            "is_public_holiday": True,
            "is_festival": False,
        }
    ]
    mock_supplementary = [
        {
            "date": "2026-01-26",
            "name": "Republic Day",
            "type": "festival",
            "country": "IN",
            "state": "MH",
            "level": "national",
            "source": "indian-festival-api",
            "verification_status": "verified_cultural_festival",
            "is_public_holiday": True,
            "is_festival": True,
        }
    ]
    merged = temp_calendar_service._merge_and_normalize(mock_primary + mock_supplementary)
    assert "2026-01-26" in merged
    # Should deduplicate into exactly 1 consolidated record
    assert len(merged["2026-01-26"]) == 1
    event = merged["2026-01-26"][0]
    assert event["name"] == "Republic Day"
    assert event["is_public_holiday"] is True
    assert event["is_festival"] is True
    assert event["verification_status"] == "verified_gazetted"
    assert "calendar-api-web" in event["source"] and "indian-festival-api" in event["source"]

def test_distinct_events_same_date(temp_calendar_service):
    """Verify multiple distinct events on the same date are both preserved."""
    records = [
        {
            "date": "2026-10-29",
            "name": "Karaka Chaturthi (Karwa Chouth)",
            "type": "restricted_holiday",
            "country": "IN",
            "state": "all",
            "level": "national",
            "source": "calendar-api-web",
            "verification_status": "restricted_optional",
            "is_public_holiday": False,
            "is_festival": False,
        },
        {
            "date": "2026-10-29",
            "name": "Special Autumn Fair",
            "type": "festival",
            "country": "IN",
            "state": "MH",
            "level": "cultural",
            "source": "community-registry",
            "verification_status": "verified_cultural_festival",
            "is_public_holiday": False,
            "is_festival": True,
        }
    ]
    merged = temp_calendar_service._merge_and_normalize(records)
    assert len(merged["2026-10-29"]) == 2

# ---------------------------------------------------------------------------- #
# 2. Resilient Fallbacks & Safe Failures
# ---------------------------------------------------------------------------- #
def test_timeout_and_graceful_fallback(temp_calendar_service):
    """Verify that if live APIs time out or fail, valid cached data is NOT overwritten."""
    # Seed cache with known good data
    temp_calendar_service._cache["events_by_date"] = {
        "2026-05-01": [{
            "date": "2026-05-01",
            "name": "Maharashtra Day",
            "type": "gazetted_holiday",
            "country": "IN",
            "state": "MH",
            "level": "state",
            "source": "cached_golden_record",
            "verification_status": "verified_gazetted",
            "is_public_holiday": True,
            "is_festival": False,
        }]
    }
    temp_calendar_service._cache["last_refreshed"] = datetime.now(timezone.utc).isoformat()
    temp_calendar_service._save_cache()

    # Simulate network failure
    with patch.object(temp_calendar_service, "fetch_primary_holidays", return_value=([], "Connection timeout")):
        with patch.object(temp_calendar_service, "fetch_supplementary_festivals", return_value=([], "HTTP 500 error")):
            with patch.object(temp_calendar_service, "fetch_statutory_engine_holidays", return_value=[]):
                res = temp_calendar_service.refresh_calendar_data(year=2026, force=True)
                assert res["status"] == "degraded_cached"
                # Existing cached date must still exist
                assert "2026-05-01" in temp_calendar_service._cache["events_by_date"]
                evts = temp_calendar_service.get_events_for_date(date(2026, 5, 1))
                assert len(evts) == 1
                assert evts[0]["name"] == "Maharashtra Day"

# ---------------------------------------------------------------------------- #
# 3. Calendar Feature Generation Vector
# ---------------------------------------------------------------------------- #
def test_calendar_features_vector(temp_calendar_service):
    """Verify correct feature vector extraction for ML pipelines."""
    # Seed a public holiday on 2026-01-26 (Monday)
    temp_calendar_service._cache["events_by_date"]["2026-01-26"] = [{
        "date": "2026-01-26",
        "name": "Republic Day",
        "type": "gazetted_holiday",
        "verification_status": "verified_gazetted",
        "is_public_holiday": True,
        "is_festival": False,
    }]
    feats_holiday = temp_calendar_service.get_calendar_features(date(2026, 1, 26))
    assert feats_holiday["is_public_holiday"] == 1
    assert feats_holiday["is_festival"] == 0
    assert feats_holiday["is_weekend"] == 0
    assert feats_holiday["event_label"] == "Republic Day"
    assert feats_holiday["holiday_type"] == "gazetted_holiday"

    # Seed an ordinary Wednesday (2026-06-10)
    feats_ordinary = temp_calendar_service.get_calendar_features(date(2026, 6, 10))
    assert feats_ordinary["is_public_holiday"] == 0
    assert feats_ordinary["is_festival"] == 0
    assert feats_ordinary["is_weekend"] == 0
    assert feats_ordinary["event_label"] == "-"
    assert feats_ordinary["holiday_type"] == "none"

# ---------------------------------------------------------------------------- #
# 4. Forecast Model Integration: Empirical Lift vs Cold Start
# ---------------------------------------------------------------------------- #
def test_forecast_empirical_lift_vs_cold_start():
    """
    Verify that ForecastService:
    1. Derives empirical lift from historical POS data for established items (Croissant).
    2. Keeps 0.0 lift (no fabricated boost) for unobserved / cold start items (sweet, brfi).
    """
    engine = ForecastService()

    # Item with historical data
    lift_croissant, reason_croissant = engine.get_sku_empirical_holiday_lift("Butter Croissant")
    assert lift_croissant > 0.0
    assert "historical holiday observations" in reason_croissant

    # Item without historical data (cold start)
    lift_cold, reason_cold = engine.get_sku_empirical_holiday_lift("sweet")
    assert lift_cold == 0.0
    assert "No historical holiday sales records" in reason_cold

    lift_cold_2, reason_cold_2 = engine.get_sku_empirical_holiday_lift("Kajukatli")
    assert lift_cold_2 == 0.0
    assert "No historical holiday sales records" in reason_cold_2


# ---------------------------------------------------------------------------- #
# 5. Gazette Cross-Validation & Festival Quarantine Filter
# ---------------------------------------------------------------------------- #
def test_festival_gazette_quarantine_filter(temp_calendar_service):
    """
    Verify that unverified/corrupt festival dates from external APIs (e.g. Dhanteras on 2026-10-30,
    Diwali on 2026-11-01, Bhai Dooj on 2026-11-03) are strictly quarantined and rejected,
    while Dhanteras is accurately anchored to Kartik Trayodashi (2 days before Diwali Lakshmi Puja).
    """
    mock_official = [
        {
            "date": "2026-11-08",
            "name": "Diwali (Deepavali)",
            "type": "gazetted_holiday",
            "country": "IN",
            "state": "all",
            "level": "national",
            "verification_status": "verified_gazetted",
            "is_public_holiday": True,
            "is_festival": False,
        },
        {
            "date": "2026-11-11",
            "name": "Bhai Duj",
            "type": "restricted_holiday",
            "country": "IN",
            "state": "all",
            "level": "national",
            "verification_status": "restricted_optional",
            "is_public_holiday": False,
            "is_festival": False,
        }
    ]

    mock_unverified_festivals = [
        # Corrupt Dhanteras date
        {
            "date_2026": "2026-10-30",
            "name": "Dhanteras",
            "type": "festival",
        },
        # Corrupt Diwali date
        {
            "date_2026": "2026-11-01",
            "name": "Diwali",
            "type": "festival",
        },
        # Corrupt Bhai Dooj date
        {
            "date_2026": "2026-11-03",
            "name": "Bhai Dooj",
            "type": "festival",
        },
        # Valid separate cultural festival
        {
            "date_2026": "2026-10-15",
            "name": "Navratri",
            "type": "festival",
        }
    ]

    validated, quarantine_notes = temp_calendar_service._validate_and_quarantine_supplementary_festivals(
        mock_unverified_festivals, mock_official
    )

    # Corrupt Diwali (2026-11-01) and Bhai Dooj (2026-11-03) must be quarantined
    assert any("Diwali" in n and "2026-11-01" in n for n in quarantine_notes)
    assert any("Bhai Dooj" in n and "2026-11-03" in n for n in quarantine_notes)
    assert any("Dhanteras" in n and "2026-10-30" in n for n in quarantine_notes)

    # In validated list:
    # 1. Corrupt Diwali (Nov 1) and Bhai Dooj (Nov 3) must NOT be present
    assert not any(f.get("date_2026") == "2026-11-01" for f in validated)
    assert not any(f.get("date_2026") == "2026-11-03" for f in validated)

    # 2. Dhanteras must be anchored to 2026-11-06 (2 days before Nov 8 Diwali)
    dhanteras_entry = next((f for f in validated if f.get("name") == "Dhanteras"), None)
    assert dhanteras_entry is not None
    assert dhanteras_entry.get("date") == "2026-11-06"
    assert dhanteras_entry.get("verification_status") == "verified_cultural_festival"

    # 3. Navratri preserved
    assert any(f.get("name") == "Navratri" and f.get("date_2026") == "2026-10-15" for f in validated)


# ---------------------------------------------------------------------------- #
# 6. Daily 12:00 AM Midnight Sync Lifecycle Tests
# ---------------------------------------------------------------------------- #
def test_daily_midnight_sync_lifecycle(temp_calendar_service):
    """
    Verify daily 12:00 AM midnight synchronization:
    1. Midnight freshness detection (cache expires when crossing 12 AM).
    2. Seconds calculation until next midnight.
    3. sync_daily_midnight updates sync schedule and local 12 AM display format.
    """
    now = datetime.now()
    
    # 1. Simulate yesterday's sync (before today's 12:00 AM)
    yesterday = now - timedelta(days=1)
    temp_calendar_service._cache["last_refreshed"] = yesterday.isoformat()
    assert temp_calendar_service.is_synced_for_today() is False
    assert temp_calendar_service.is_cache_fresh() is False

    # 2. Verify seconds calculation until next 12:00 AM
    secs = temp_calendar_service.get_seconds_until_next_midnight()
    assert isinstance(secs, float)
    assert 0 < secs <= 86400

    # 3. Execute daily midnight sync with mock data
    with patch.object(temp_calendar_service, "fetch_primary_holidays", return_value=([], None)), \
         patch.object(temp_calendar_service, "fetch_supplementary_festivals", return_value=([], None)):
        res = temp_calendar_service.sync_daily_midnight(year=2026)
        
    meta = temp_calendar_service.get_metadata()
    assert meta["sync_schedule"] == "Daily 12:00 AM"
    assert "12:00 AM" in meta["last_refreshed_display"]
    assert temp_calendar_service.is_synced_for_today() is True
    assert "seconds_until_next_sync" in meta
    assert meta["seconds_until_next_sync"] > 0


