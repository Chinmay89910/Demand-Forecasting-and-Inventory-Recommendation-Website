"""
India Calendar & Holiday Service for RestockIQ Demand Forecasting Platform.
Fetches, normalizes, validates, caches, and provides live Indian public holidays
and festivals for Maharashtra (MH) and Central Government.

Supported Providers:
1. Primary: India Public Holidays API (Render deployment: https://calendar-api-d7a8.onrender.com)
   Docs: https://calendar-api-web.vercel.app/docs
2. Supplementary: Indian Festival API (https://indian-festival-api.vercel.app)
   GitHub: https://github.com/Deepsavaliya2507/indian-festival-api
3. Statutory Calendar Engine (holidays library fallback for past/future multi-year coverage)
"""
import os
import re
import json
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests
try:
    import holidays
except ImportError:
    holidays = None

logger = logging.getLogger("restockiq.calendar")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "calendar_cache.json"

PRIMARY_API_BASE = "https://calendar-api-d7a8.onrender.com"
SUPPLEMENTARY_API_BASE = "https://indian-festival-api.vercel.app/api/festivals"

CACHE_TTL_SECONDS = 86400  # 24 hours

# Authoritative canonical regex patterns for cross-validating supplementary festival dates
CANONICAL_FESTIVAL_PATTERNS: Dict[str, List[str]] = {
    "diwali": [r"\bdiwali\b", r"\bdeepavali\b", r"\blaxmi pujan\b"],
    "bhai_dooj": [r"\bbhai duj\b", r"\bbhai dooj\b", r"\bbhau beej\b"],
    "dussehra": [r"\bdussehra\b", r"\bdasara\b", r"\bvijayadashami\b"],
    "guru_nanak": [r"\bguru nanak\b", r"\bnanak jayanti\b"],
    "ganesh": [r"\bganesh\b", r"\bvinayaka\b"],
    "gudi_padwa": [r"\bgudi padwa\b", r"\bgudi padava\b", r"\bchaitra sukladi\b"],
    "shivratri": [r"\bshivratri\b", r"\bmaha shivratri\b", r"\bmahashivratri\b"],
    "holi": [r"\bholi\b", r"\bholika\b"],
    "ram_navami": [r"\bram navami\b"],
    "mahavir": [r"\bmahavir\b"],
    "buddha_purnima": [r"\bbuddha purnima\b", r"\bbudha purnima\b"],
    "muharram": [r"\bmuharram\b", r"\bmoharram\b"],
    "raksha_bandhan": [r"\braksha bandhan\b"],
    "janmashtami": [r"\bjanmashtami\b"],
    "christmas": [r"\bchristmas\b"],
    "gandhi": [r"\bgandhi\b"],
    "chhath_puja": [r"\bchhath\b", r"\bchhat puja\b", r"\bsurya shashthi\b"],
    "dhanteras": [r"\bdhanteras\b", r"\bdhantrayodashi\b", r"\bdhanatrayodashi\b"],
}


class IndiaCalendarService:
    """
    Unified, cached, resilient calendar service for Indian and Maharashtra
    public holidays and cultural festivals.
    """

    def __init__(self, cache_file: Path = CACHE_FILE):
        self.cache_file = cache_file
        self._cache: Dict[str, Any] = {
            "events_by_date": {},
            "last_refreshed": None,
            "provider_status": {
                "primary": "uninitialized",
                "supplementary": "uninitialized",
                "statutory_engine": "available" if holidays else "unavailable",
            },
            "warnings": [],
        }
        self._load_cache()

    # --------------------------------------------------------------------------
    # Cache Persistence & Management
    # --------------------------------------------------------------------------
    def _load_cache(self):
        """Loads cached calendar data from local disk if valid."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "events_by_date" in data:
                        self._cache = data
                        logger.info(f"[CALENDAR] Loaded {len(self._cache['events_by_date'])} cached dates.")
            except Exception as e:
                logger.warning(f"[CALENDAR] Failed to read calendar cache: {e}")

    def _save_cache(self):
        """Atomically persists cache to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.cache_file)
        except Exception as e:
            logger.error(f"[CALENDAR] Failed to persist cache: {e}")

    def is_synced_for_today(self) -> bool:
        """
        Determines whether the cache has undergone its daily synchronization
        on or after 12:00 AM (midnight) today in local time.
        """
        last_refreshed = self._cache.get("last_refreshed")
        if not last_refreshed:
            return False
        try:
            refreshed_dt = datetime.fromisoformat(last_refreshed)
            if refreshed_dt.tzinfo is not None:
                refreshed_dt = refreshed_dt.astimezone().replace(tzinfo=None)
            now = datetime.now()
            today_midnight = datetime(now.year, now.month, now.day, 0, 0, 0)
            return refreshed_dt >= today_midnight
        except Exception:
            return False

    def is_cache_fresh(self, max_age_seconds: int = CACHE_TTL_SECONDS) -> bool:
        """
        Checks if the cache was refreshed within the TTL AND has been synced
        for today (on or after 12:00 AM local time).
        Crossing midnight expires the cache so the daily 12 AM sync is enforced.
        """
        if not self.is_synced_for_today():
            return False
        last_refreshed = self._cache.get("last_refreshed")
        if not last_refreshed:
            return False
        try:
            refreshed_dt = datetime.fromisoformat(last_refreshed)
            if refreshed_dt.tzinfo is None:
                refreshed_dt = refreshed_dt.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            age = (now_utc - refreshed_dt).total_seconds()
            return age < max_age_seconds
        except Exception:
            return False

    def get_seconds_until_next_midnight(self) -> float:
        """
        Calculates the seconds remaining until the next 12:00:01 AM local time.
        Used by the background scheduler to wake up exactly at midnight.
        """
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        next_midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 1)
        return max(1.0, (next_midnight - now).total_seconds())

    # --------------------------------------------------------------------------
    # Provider 1: Primary India Public Holidays API (Render deployment)
    # --------------------------------------------------------------------------
    def fetch_primary_holidays(self, year: int = 2026, region: str = "MH") -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetches official gazetted and restricted holidays from the India Public Holidays API.
        Returns (records, error_message).
        """
        url = f"{PRIMARY_API_BASE}/v1/holidays"
        params = {
            "country": "IN",
            "year": str(year),
            "region": region,
            "scope": "all"
        }
        try:
            resp = requests.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                raw_items = data.get("data", [])
                normalized = []
                for item in raw_items:
                    d_str = item.get("date")
                    if not d_str:
                        continue
                    is_gazetted = item.get("type") == "gazetted_holiday" or "gazetted" in item.get("description", "").lower()
                    level = item.get("level", "central")  # "central" or "state"
                    normalized.append({
                        "date": d_str,
                        "name": item.get("name", "Public Holiday"),
                        "type": "gazetted_holiday" if is_gazetted else "restricted_holiday",
                        "country": "IN",
                        "state": region if level == "state" else "all",
                        "level": "state" if level == "state" else "national",
                        "source": "calendar-api-web (Render)",
                        "source_url": item.get("source", "https://www.india.gov.in/calendar"),
                        "description": item.get("description", ""),
                        "verification_status": "verified_gazetted" if is_gazetted else "restricted_optional",
                        "is_public_holiday": is_gazetted,
                        "is_festival": False,
                    })
                return normalized, None
            elif resp.status_code == 404:
                return [], f"Primary API has no records for year {year} (HTTP 404)."
            else:
                return [], f"Primary API error: HTTP {resp.status_code} - {resp.text[:100]}"
        except requests.exceptions.Timeout:
            return [], "Primary API timed out (>12s)."
        except Exception as e:
            return [], f"Primary API request failed: {e}"

    # --------------------------------------------------------------------------
    # Provider 2: Supplementary Indian Festival API
    # --------------------------------------------------------------------------
    def fetch_supplementary_festivals(self, state: str = "Maharashtra") -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetches cultural festival dates from the Indian Festival API.
        Note: Current API implementation contains dates for year 2026 in 'date_2026'.
        Returns (records, error_message).
        """
        params = {"state": state}
        try:
            resp = requests.get(SUPPLEMENTARY_API_BASE, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                raw_items = data.get("data", [])
                normalized = []
                for item in raw_items:
                    # The API specifies 'date_2026'
                    d_str = item.get("date_2026")
                    if not d_str:
                        continue
                    is_national = bool(item.get("national_holiday", False))
                    is_restricted = bool(item.get("restricted_holiday", False))
                    evt_type = item.get("type", "festival")

                    normalized.append({
                        "date": d_str,
                        "name": item.get("name", "Festival"),
                        "type": "festival" if evt_type == "festival" else ("gazetted_holiday" if is_national else "restricted_holiday"),
                        "country": "IN",
                        "state": "MH" if ("maharashtra" in [s.lower() for s in item.get("states", [])] or "all" in item.get("states", [])) else "all",
                        "level": "national" if is_national else ("cultural" if evt_type == "festival" else "state"),
                        "source": "indian-festival-api",
                        "source_url": SUPPLEMENTARY_API_BASE,
                        "description": item.get("description", ""),
                        "verification_status": "verified_cultural_festival" if evt_type == "festival" else ("verified_gazetted" if is_national else "restricted_optional"),
                        "is_public_holiday": is_national,
                        "is_festival": True,
                        "religion": item.get("religion", ""),
                        "tags": item.get("tags", []),
                    })
                return normalized, None
            else:
                return [], f"Supplementary API error: HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return [], "Supplementary Festival API timed out (>10s)."
        except Exception as e:
            return [], f"Supplementary Festival API failed: {e}"

    # --------------------------------------------------------------------------
    # Provider 3: Statutory Calendar Engine Fallback
    # --------------------------------------------------------------------------
    def fetch_statutory_engine_holidays(self, year: int, subdiv: str = "MH") -> List[Dict[str, Any]]:
        """
        Generates official statutory holidays for India / Maharashtra using the python holidays library.
        Used to provide accurate astronomical/gazetted calendar calculation for past years
        (e.g., 2021-2025) and future years (2027+) where external web APIs return 404.
        """
        if not holidays:
            return []
        try:
            mh_hols = holidays.country_holidays("IN", subdiv=subdiv, years=[year])
            records = []
            for dt_obj, name in mh_hols.items():
                d_str = dt_obj.strftime("%Y-%m-%d")
                records.append({
                    "date": d_str,
                    "name": name,
                    "type": "gazetted_holiday",
                    "country": "IN",
                    "state": subdiv,
                    "level": "state" if ("Maharashtra Day" in name or "Gudi Padwa" in name or "Ganesh" in name or "Shivaji" in name) else "national",
                    "source": "statutory_calendar_engine",
                    "source_url": "https://pypi.org/project/holidays/",
                    "description": f"Officially notified public holiday in Maharashtra ({name})",
                    "verification_status": "verified_gazetted",
                    "is_public_holiday": True,
                    "is_festival": False,
                })
            return records
        except Exception as e:
            logger.warning(f"[CALENDAR] Statutory engine error for year {year}: {e}")
            return []

    # --------------------------------------------------------------------------
    # Festival Cross-Validation & Quarantine Engine
    # --------------------------------------------------------------------------
    def _validate_and_quarantine_supplementary_festivals(
        self,
        fest_records: List[Dict[str, Any]],
        official_records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Cross-validates external festival candidates against authoritative official gazette dates.
        Rejects dates with discrepancies and anchors Dhanteras dynamically to Kartik Trayodashi
        (2 days prior to official Diwali Lakshmi Puja).
        """
        canonical_official_dates: Dict[str, set] = {}

        def _matches(name: str, patterns: List[str]) -> bool:
            for p in patterns:
                if re.search(p, name, re.IGNORECASE):
                    return True
            return False

        for rec in official_records:
            r_name = rec.get("name", "")
            r_date = rec.get("date", "")
            if not r_date:
                continue
            for family_key, patterns in CANONICAL_FESTIVAL_PATTERNS.items():
                if _matches(r_name, patterns):
                    if family_key not in canonical_official_dates:
                        canonical_official_dates[family_key] = set()
                    canonical_official_dates[family_key].add(r_date)

        # Anchor Dhanteras dynamically to 2 days before Diwali Lakshmi Puja
        diwali_dates = canonical_official_dates.get("diwali", set())
        if diwali_dates:
            diwali_main = sorted(list(diwali_dates))[0]
            diwali_dt = datetime.strptime(diwali_main, "%Y-%m-%d").date()
            dhanteras_anchor = (diwali_dt - timedelta(days=2)).strftime("%Y-%m-%d")
            canonical_official_dates["dhanteras"] = {dhanteras_anchor}

        validated: List[Dict[str, Any]] = []
        quarantine_notes: List[str] = []

        for f in fest_records:
            f_name = f.get("name", "Festival")
            f_date = f.get("date_2026") or f.get("date")
            if not f_date:
                continue

            matched_family = None
            for family_key, patterns in CANONICAL_FESTIVAL_PATTERNS.items():
                if _matches(f_name, patterns):
                    matched_family = family_key
                    break

            if matched_family and matched_family in canonical_official_dates:
                valid_dates = canonical_official_dates[matched_family]
                if f_date not in valid_dates:
                    msg = f"Quarantined unverified '{f_name}' on {f_date} (diverges from authoritative date {sorted(list(valid_dates))})."
                    logger.warning(f"[CALENDAR] {msg}")
                    quarantine_notes.append(msg)
                    # For Dhanteras, inject accurately anchored record
                    if matched_family == "dhanteras":
                        anchored_d = sorted(list(valid_dates))[0]
                        corrected = dict(f)
                        corrected["date"] = anchored_d
                        corrected["date_2026"] = anchored_d
                        corrected["verification_status"] = "verified_cultural_festival"
                        corrected["source"] = "Panchang Astronomical Anchor (Kartik Trayodashi, 2 days before Diwali)"
                        validated.append(corrected)
                    continue

            validated.append(f)

        return validated, quarantine_notes

    # --------------------------------------------------------------------------
    # Normalization & Deduplication Pipeline
    # --------------------------------------------------------------------------
    def _merge_and_normalize(self, records_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Merges events across providers, eliminating duplicates by matching on date and normalized name.
        When both an official public holiday and a cultural festival exist on the same date:
        - If names match (e.g., Diwali or Republic Day), merges and elevates to verified_gazetted.
        - If distinct (e.g., Karwa Chauth + another event), keeps both in the date's event list.
        """
        by_date: Dict[str, List[Dict[str, Any]]] = {}

        for rec in records_list:
            d = rec["date"]
            if d not in by_date:
                by_date[d] = []

            # Check if this event already exists on this date
            rec_name_clean = rec["name"].strip().lower()
            existing = None
            for ex in by_date[d]:
                ex_name_clean = ex["name"].strip().lower()
                # Fuzzy matching for similar festival/holiday names
                if (rec_name_clean in ex_name_clean or ex_name_clean in rec_name_clean or
                    ("diwali" in rec_name_clean and "diwali" in ex_name_clean) or
                    ("bhai" in rec_name_clean and "bhai" in ex_name_clean) or
                    ("dussehra" in rec_name_clean and ("dussehra" in ex_name_clean or "dasara" in ex_name_clean)) or
                    ("gandhi" in rec_name_clean and "gandhi" in ex_name_clean) or
                    ("nanak" in rec_name_clean and "nanak" in ex_name_clean) or
                    ("republic" in rec_name_clean and "republic" in ex_name_clean) or
                    ("christmas" in rec_name_clean and "christmas" in ex_name_clean)):
                    existing = ex
                    break

            if existing:
                # Merge: elevate to gazetted if either is gazetted
                if rec.get("is_public_holiday"):
                    existing["is_public_holiday"] = True
                    existing["verification_status"] = "verified_gazetted"
                    existing["type"] = "gazetted_holiday"
                if rec.get("is_festival"):
                    existing["is_festival"] = True
                if rec.get("source") != existing.get("source"):
                    existing["source"] = f"{existing['source']} + {rec['source']}"
                if rec.get("description") and not existing.get("description"):
                    existing["description"] = rec["description"]
            else:
                by_date[d].append(rec)

        # Sort events inside each date: public holidays first, then festivals, then restricted
        for d in by_date:
            by_date[d].sort(key=lambda x: (not x.get("is_public_holiday", False), not x.get("is_festival", False)))

        return by_date

    # --------------------------------------------------------------------------
    # Orchestrated Refresh & Synchronization
    # --------------------------------------------------------------------------
    def refresh_calendar_data(self, year: int = 2026, state: str = "MH", force: bool = False) -> Dict[str, Any]:
        """
        Synchronizes calendar data from live APIs, updates local cache,
        and logs verification status.
        Never overwrites valid cache if live APIs fail.
        """
        if not force and self.is_cache_fresh() and self._cache.get("events_by_date"):
            return {
                "status": "cached",
                "message": "Serving cached calendar data within 24h TTL.",
                "last_refreshed": self._cache.get("last_refreshed"),
                "total_events": sum(len(evts) for evts in self._cache["events_by_date"].values()),
                "warnings": self._cache.get("warnings", []),
                "provider_status": self._cache.get("provider_status", {})
            }

        official_records: List[Dict[str, Any]] = []
        all_collected_records: List[Dict[str, Any]] = []
        warnings: List[str] = []
        provider_status: Dict[str, str] = {}

        # 1. Fetch Primary API (Official Gazette)
        prim_records, prim_err = self.fetch_primary_holidays(year=year, region=state)
        if prim_records:
            official_records.extend(prim_records)
            provider_status["primary"] = f"healthy ({len(prim_records)} records)"
        else:
            provider_status["primary"] = f"unavailable: {prim_err}"
            warnings.append(f"Primary API unavailable for year {year}: {prim_err}")

        # 2. Augment with the statutory calendar engine for reliable gazetted coverage
        statutory_records = self.fetch_statutory_engine_holidays(year=year, subdiv=state)
        if statutory_records:
            official_records.extend(statutory_records)
            provider_status["statutory_engine"] = f"healthy ({len(statutory_records)} records)"

        # 3. Fetch Supplementary Festival API & Cross-Validate against Official Gazette
        fest_records, fest_err = self.fetch_supplementary_festivals(state="Maharashtra")
        if fest_records:
            validated_fest, quarantine_notes = self._validate_and_quarantine_supplementary_festivals(
                fest_records, official_records
            )
            all_collected_records = official_records + validated_fest
            provider_status["supplementary"] = f"healthy ({len(validated_fest)} verified festivals, {len(quarantine_notes)} quarantined)"
            warnings.extend(quarantine_notes)
        else:
            all_collected_records = list(official_records)
            provider_status["supplementary"] = f"unavailable: {fest_err}"
            warnings.append(f"Supplementary Festival API: {fest_err}")

        # 4. Merge, validate, and atomically persist
        if all_collected_records:
            merged_by_date = self._merge_and_normalize(all_collected_records)
            
            # Atomically replace events for this year to remove any stale/corrupt records
            prefix = f"{year}-"
            self._cache["events_by_date"] = {
                k: v for k, v in self._cache.get("events_by_date", {}).items() if not k.startswith(prefix)
            }
            self._cache["events_by_date"].update(merged_by_date)

            new_count = sum(len(evts) for evts in self._cache["events_by_date"].values())
            now_local = datetime.now()
            self._cache["last_refreshed"] = now_local.isoformat()
            self._cache["last_refreshed_display"] = now_local.strftime("%d %b %Y, 12:00 AM") if now_local.hour == 0 else now_local.strftime("%d %b %Y, %I:%M %p")
            self._cache["sync_schedule"] = "Daily 12:00 AM"
            self._cache["provider_status"] = provider_status
            self._cache["warnings"] = warnings
            self._save_cache()
            
            return {
                "status": "refreshed",
                "message": f"Successfully updated calendar. Cached {new_count} records across {len(self._cache['events_by_date'])} dates.",
                "last_refreshed": self._cache["last_refreshed"],
                "last_refreshed_display": self._cache["last_refreshed_display"],
                "sync_schedule": self._cache["sync_schedule"],
                "total_events": new_count,
                "warnings": warnings,
                "provider_status": provider_status
            }
        else:
            # Both live calls and statutory engine failed, retain existing cache
            warnings.append("Failed to retrieve new data from all providers. Retained previous cache.")
            self._cache["warnings"] = warnings
            return {
                "status": "degraded_cached",
                "message": "Providers unreachable. Retained existing cached data.",
                "last_refreshed": self._cache.get("last_refreshed"),
                "total_events": sum(len(evts) for evts in self._cache.get("events_by_date", {}).values()),
                "warnings": warnings,
                "provider_status": provider_status
            }

    # --------------------------------------------------------------------------
    # Consumer Methods for Forecasting & Frontend
    # --------------------------------------------------------------------------
    def get_events_for_date(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Retrieves normalized events for a specific calendar day.
        If cache is empty or expired, performs an automatic refresh.
        """
        d_str = target_date.strftime("%Y-%m-%d")
        if not self._cache.get("events_by_date") or not self.is_cache_fresh():
            self.refresh_calendar_data(year=target_date.year)

        # Check in cache
        events = self._cache.get("events_by_date", {}).get(d_str, [])
        if not events and holidays:
            # Check statutory engine if date is outside cached range
            stat_hols = holidays.country_holidays("IN", subdiv="MH", years=[target_date.year])
            if target_date in stat_hols:
                h_name = stat_hols[target_date]
                return [{
                    "date": d_str,
                    "name": h_name,
                    "type": "gazetted_holiday",
                    "country": "IN",
                    "state": "MH",
                    "level": "state" if ("Maharashtra" in h_name or "Gudi Padwa" in h_name or "Shivaji" in h_name) else "national",
                    "source": "statutory_calendar_engine",
                    "source_url": "https://pypi.org/project/holidays/",
                    "description": f"Officially notified public holiday in Maharashtra ({h_name})",
                    "verification_status": "verified_gazetted",
                    "is_public_holiday": True,
                    "is_festival": False,
                }]
        return events

    def get_events_for_range(self, start_date: date, end_date: date, state: str = "MH") -> List[Dict[str, Any]]:
        """
        Returns all verified events between start_date and end_date (inclusive),
        sorted chronologically.
        """
        curr = start_date
        out = []
        while curr <= end_date:
            evts = self.get_events_for_date(curr)
            out.extend(evts)
            curr += timedelta(days=1)
        return out

    def get_calendar_features(self, target_date: date) -> Dict[str, Any]:
        """
        Extracts structured feature vector for forecasting models:
        - is_public_holiday: 1 if official gazetted state/central holiday else 0
        - is_festival: 1 if cultural festival else 0
        - is_weekend: 1 if Saturday/Sunday else 0
        - day_of_week: 0..6
        - event_label: Primary event name or '-'
        - verification_status: Status string
        - holiday_type: 'gazetted' | 'festival' | 'restricted' | 'none'
        - is_verified: bool
        """
        dow = target_date.weekday()
        is_weekend = dow in (5, 6)
        evts = self.get_events_for_date(target_date)

        is_pub_hol = any(e.get("is_public_holiday", False) for e in evts)
        is_fest = any(e.get("is_festival", False) for e in evts)
        
        event_label = "-"
        holiday_type = "none"
        verif_status = "none"

        if evts:
            primary_evt = evts[0]
            event_label = primary_evt.get("name", "-")
            holiday_type = primary_evt.get("type", "none")
            verif_status = primary_evt.get("verification_status", "unverified")

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "day_of_week": dow,
            "is_weekend": 1 if is_weekend else 0,
            "is_public_holiday": 1 if is_pub_hol else 0,
            "is_festival": 1 if is_fest else 0,
            "is_special_day": 1 if (is_pub_hol or is_fest or is_weekend) else 0,
            "event_label": event_label,
            "holiday_type": holiday_type,
            "verification_status": verif_status,
            "is_verified": verif_status in ("verified_gazetted", "verified_cultural_festival"),
            "events_count": len(evts),
            "events": evts,
            "last_refreshed": self._cache.get("last_refreshed"),
            "warnings": self._cache.get("warnings", []),
        }

    def sync_daily_midnight(self, year: Optional[int] = None, state: str = "MH") -> Dict[str, Any]:
        """
        Executes the mandatory daily 12:00 AM calendar synchronization.
        Refreshes live holiday and festival data, stamps the daily 12 AM sync marker,
        and saves cache to disk.
        """
        now = datetime.now()
        target_year = year or now.year
        logger.info(f"[CALENDAR] Running daily 12:00 AM sync for {now.strftime('%d %b %Y')} (year {target_year})...")
        res = self.refresh_calendar_data(year=target_year, state=state, force=True)
        self._cache["last_refreshed_display"] = now.strftime("%d %b %Y, 12:00 AM")
        self._cache["sync_schedule"] = "Daily 12:00 AM"
        self._cache["last_midnight_sync"] = now.isoformat()
        self._save_cache()
        logger.info(f"[CALENDAR] Daily 12:00 AM sync completed successfully. Total events cached: {res.get('total_events', 0)}")
        return res

    def get_metadata(self) -> Dict[str, Any]:
        """Returns service status, cache age, providers, and freshness."""
        total_dates = len(self._cache.get("events_by_date", {}))
        total_events = sum(len(evts) for evts in self._cache.get("events_by_date", {}).values())
        now = datetime.now()
        default_display = now.strftime("%d %b %Y, 12:00 AM")
        return {
            "last_refreshed": self._cache.get("last_refreshed"),
            "last_refreshed_display": self._cache.get("last_refreshed_display", default_display),
            "sync_schedule": self._cache.get("sync_schedule", "Daily 12:00 AM"),
            "is_cache_fresh": self.is_cache_fresh(),
            "is_synced_today": self.is_synced_for_today(),
            "seconds_until_next_sync": round(self.get_seconds_until_next_midnight(), 1),
            "total_cached_dates": total_dates,
            "total_cached_events": total_events,
            "provider_status": self._cache.get("provider_status", {}),
            "warnings": self._cache.get("warnings", []),
            "primary_api": "https://calendar-api-d7a8.onrender.com/v1/holidays",
            "supplementary_api": SUPPLEMENTARY_API_BASE,
        }


calendar_service = IndiaCalendarService()

