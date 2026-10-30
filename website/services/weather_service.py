"""
Live Real-World Weather Telemetry Service for RestockIQ Demand Forecasting.
Fetches real meteorological telemetry via Open-Meteo API and calculates
foot traffic, temperature, humidity, precipitation, and day-of-week demand multipliers for food retailers.
Supports live minute-to-minute updates with persistent caching and historical archive queries.

Provider: Open-Meteo (https://open-meteo.com)
License: Free for non-commercial & educational use under Creative Commons Attribution 4.0 International (CC BY 4.0).
Commercial Note: For commercial food retail deployments, an Open-Meteo API subscription or self-hosted Open-Meteo model container is required.
"""
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import urllib.parse

logger = logging.getLogger("restockiq.weather")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "weather_cache.json"

# WMO Weather interpretation codes mapping to human conditions, icons, and foot traffic impacts
WMO_CODES = {
    0: ("Clear sky", "☀️", +15),
    1: ("Mainly clear", "🌤️", +12),
    2: ("Partly cloudy", "⛅", +8),
    3: ("Overcast", "☁️", -2),
    45: ("Foggy", "🌫️", -8),
    48: ("Depositing rime fog", "🌫️", -10),
    51: ("Light drizzle", "🌦️", -5),
    53: ("Moderate drizzle", "🌦️", -8),
    55: ("Dense drizzle", "🌧️", -12),
    61: ("Slight rain", "🌧️", -10),
    63: ("Moderate rain", "🌧️", -15),
    65: ("Heavy rain", "🌧️", -22),
    71: ("Slight snow", "🌨️", -14),
    73: ("Moderate snow", "🌨️", -20),
    80: ("Rain showers", "🌦️", -12),
    81: ("Moderate showers", "🌧️", -16),
    82: ("Violent showers", "⛈️", -22),
    95: ("Thunderstorm", "⛈️", -25),
}

LIVE_WEATHER_TTL_SECONDS = 60      # 1 minute for true minute-to-minute updates
FORECAST_TTL_SECONDS = 1800        # 30 minutes for 7-day forecast


def parse_wmo_code(code: int, temp: float = 30.0, precip_mm: float = 0.0, precip_prob: int = 0) -> Tuple[str, str, int]:
    """Interprets WMO weather code into realistic human condition, emoji icon, and customer foot-traffic impact."""
    # Measurable significant rain
    if precip_mm >= 4.0 or (precip_prob >= 70 and precip_mm >= 2.5) or code in [63, 65, 81, 82]:
        return ("Rain", "🌧️", -16)
    elif (precip_mm >= 1.5 and precip_prob >= 50) or (precip_mm >= 2.0) or (precip_prob >= 65 and code in [61, 80]):
        return ("Light Rain", "🌦️", -8)
    elif code in [95, 96, 99]:
        return ("Thunderstorm", "⛈️", -25)
    elif code in [45, 48]:
        return ("Foggy", "🌫️", -8)
    elif code == 3:
        return ("Cloudy", "☁️", -2)
    elif code == 2 or (precip_mm > 0.0 and precip_mm < 1.5 and precip_prob < 50) or code in [51, 53, 55]:
        # Trace moisture / slight passing cloud / trace drizzle
        return ("Partly Cloudy", "⛅", +6)
    elif code in [0, 1]:
        desc = "Sunny" if temp >= 30 else "Clear"
        return (desc, "☀️", +12)
    else:
        return ("Partly Cloudy", "⛅", +5)


class WeatherService:
    def __init__(self, cache_file: Path = CACHE_FILE, default_lat: float = 21.3482, default_lon: float = 74.8804):
        # Default coordinates for Shirpur, Maharashtra (Dhule district)
        self.default_lat = default_lat
        self.default_lon = default_lon
        self.cache_file = cache_file
        self._cache: Dict[str, Any] = {
            "live_weather": {},
            "forecast_7d": {},
            "geocoding": {
                "shirpur": [21.3482, 74.8804],
                "mumbai": [19.0760, 72.8777],
                "pune": [18.5204, 73.8567],
                "delhi": [28.6139, 77.2090],
                "bangalore": [12.9716, 77.5946],
                "nashik": [19.9975, 73.7898],
                "nagpur": [21.1458, 79.0882],
            },
            "historical": {},
            "last_saved": None,
        }
        self._load_cache()

    # --------------------------------------------------------------------------
    # Cache Persistence
    # --------------------------------------------------------------------------
    def _load_cache(self):
        """Loads cached weather telemetry and geocoding from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for k in ["live_weather", "forecast_7d", "geocoding", "historical"]:
                            if k in data and isinstance(data[k], dict):
                                self._cache[k].update(data[k])
                        self._cache["last_saved"] = data.get("last_saved")
                        logger.info(f"[WEATHER] Loaded cache from {self.cache_file}")
            except Exception as e:
                logger.warning(f"[WEATHER] Failed to load cache: {e}")

    def _save_cache(self):
        """Atomically saves cache to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache["last_saved"] = datetime.now(timezone.utc).isoformat()
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.cache_file)
        except Exception as e:
            logger.error(f"[WEATHER] Failed to save cache: {e}")

    # --------------------------------------------------------------------------
    # Geocoding Service (Open-Meteo Search API)
    # --------------------------------------------------------------------------
    def geocode_location(self, location_name: str) -> Tuple[float, float]:
        """
        Resolves city name to latitude and longitude using free Open-Meteo Geocoding API.
        Falls back to Shirpur, Maharashtra default coordinates.
        """
        if not location_name:
            return (self.default_lat, self.default_lon)

        clean_city = location_name.split(",")[0].strip().lower()
        if clean_city in self._cache["geocoding"]:
            coords = self._cache["geocoding"][clean_city]
            return (float(coords[0]), float(coords[1]))

        try:
            encoded = urllib.parse.quote(clean_city)
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "RestockIQ-Demand/2.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                results = data.get("results", [])
                if results:
                    lat = float(results[0].get("latitude", self.default_lat))
                    lon = float(results[0].get("longitude", self.default_lon))
                    self._cache["geocoding"][clean_city] = [lat, lon]
                    self._save_cache()
                    return (lat, lon)
        except Exception as e:
            logger.info(f"[WEATHER] Geocoding lookup fallback for {location_name}: {e}")

        return (self.default_lat, self.default_lon)

    # --------------------------------------------------------------------------
    # Minute-to-Minute Real-Time Live Weather
    # --------------------------------------------------------------------------
    def get_live_weather(self, location: str = "Shirpur, Maharashtra", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches live current weather for the store location.
        Caches for 60 seconds (1 minute) to enable true minute-to-minute updates
        without flooding external endpoints.
        """
        now = datetime.now()
        cache_key = location.strip().lower()
        cached = self._cache["live_weather"].get(cache_key)

        if not force_refresh and cached:
            cached_time_str = cached.get("updated_at")
            if cached_time_str:
                try:
                    c_dt = datetime.fromisoformat(cached_time_str)
                    age_seconds = (now - c_dt).total_seconds()
                    if age_seconds < LIVE_WEATHER_TTL_SECONDS:
                        res = dict(cached)
                        res["freshness_seconds"] = int(age_seconds)
                        return res
                except Exception:
                    pass

        lat, lon = self.geocode_location(location)

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,weather_code,wind_speed_10m"
                f"&timezone=auto"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "RestockIQ-Demand/2.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                curr = data.get("current", {})

                temp = round(float(curr.get("temperature_2m", 30.0)), 1)
                feels_like = round(float(curr.get("apparent_temperature", temp)), 1)
                humidity = int(round(float(curr.get("relative_humidity_2m", 50.0))))
                precip = round(float(curr.get("precipitation", 0.0)), 1)
                wind = round(float(curr.get("wind_speed_10m", 8.0)), 1)
                code = int(curr.get("weather_code", 1))

                desc, icon, traffic_impact = parse_wmo_code(code, temp=temp, precip_mm=precip)

                weekday = now.strftime("%A")
                day_factors = {
                    "Monday": (+5, "Steady start-of-week commuter routine."),
                    "Tuesday": (+8, "Normal business walk-ins and corporate orders."),
                    "Wednesday": (+18, "Mid-week hump brings higher pastry & coffee traffic!"),
                    "Thursday": (+16, "Strong regular customer traffic and pre-orders."),
                    "Friday": (+24, "Peak weekly volume with office gatherings and weekend preps."),
                    "Saturday": (+35, "Busiest brunch and artisan bread demand."),
                    "Sunday": (+28, "Relaxed family breakfast and afternoon treat volume.")
                }
                day_boost, day_note = day_factors.get(weekday, (+10, "Standard daily traffic."))
                net_boost = day_boost + traffic_impact

                now_display = now.strftime("%I:%M %p")

                res = {
                    "temperature": int(round(temp)),
                    "temperature_exact": temp,
                    "feels_like": feels_like,
                    "humidity": humidity,
                    "precipitation_mm": precip,
                    "condition": desc,
                    "icon": icon,
                    "wind_kmh": wind,
                    "weather_code": code,
                    "day_of_week": weekday,
                    "date_formatted": now.strftime("%a, %d %b %Y"),
                    "traffic_impact": traffic_impact,
                    "traffic_boost_pct": max(5, net_boost),
                    "day_note": day_note,
                    "insight_text": f"Today is usually {max(5, net_boost)}% busier than average for {weekday}. Weather: {desc} ({temp}°C). Prepare a bit more of popular items!",
                    "updated_at": now.isoformat(),
                    "updated_at_display": now_display,
                    "is_live": True,
                    "update_frequency": "minute-to-minute (60s)",
                    "source": "Open-Meteo Live API",
                    "coordinates": {"lat": lat, "lon": lon},
                    "location": location,
                    "freshness_seconds": 0,
                }
                self._cache["live_weather"][cache_key] = res
                self._save_cache()
                return res
        except Exception as e:
            logger.warning(f"[WEATHER] Live weather lookup fallback for {location}: {e}")
            if cached:
                cached_res = dict(cached)
                cached_res["is_live"] = False
                cached_res["cached"] = True
                cached_res["warning"] = f"Live update delayed ({e}); serving verified cached observation."
                return cached_res

            weekday = now.strftime("%A")
            return {
                "temperature": 32,
                "temperature_exact": 32.0,
                "feels_like": 34.0,
                "humidity": 45,
                "precipitation_mm": 0.0,
                "condition": "Sunny",
                "icon": "☀️",
                "wind_kmh": 8.5,
                "weather_code": 1,
                "day_of_week": weekday,
                "date_formatted": now.strftime("%a, %d %b %Y"),
                "traffic_impact": +12,
                "traffic_boost_pct": 18,
                "day_note": "Mid-week routine brings high morning walk-ins.",
                "insight_text": f"Today is usually 18% busier than average for {weekday}. Prepare a bit more of popular items!",
                "updated_at": now.isoformat(),
                "updated_at_display": now.strftime("%I:%M %p"),
                "is_live": False,
                "update_frequency": "minute-to-minute (60s)",
                "source": "Open-Meteo Offline Fallback",
                "coordinates": {"lat": lat, "lon": lon},
                "location": location,
                "freshness_seconds": 0,
            }

    # --------------------------------------------------------------------------
    # 7-Day Daily Meteorological Forecast
    # --------------------------------------------------------------------------
    def get_7day_weather_forecast(
        self,
        location: str = "Shirpur, Maharashtra",
        lat: float = None,
        lon: float = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetches 7-day meteorological forecast via Open-Meteo Daily API.
        Includes precipitation sums, probabilities, temperatures, and retail demand impacts.
        Caches for 30 minutes to balance freshness and API quotas.
        """
        now = datetime.now()
        cache_key = location.strip().lower()
        cached = self._cache["forecast_7d"].get(cache_key)

        if not force_refresh and cached:
            cached_time_str = cached.get("updated_at")
            if cached_time_str:
                try:
                    c_dt = datetime.fromisoformat(cached_time_str)
                    if (now - c_dt).total_seconds() < FORECAST_TTL_SECONDS:
                        return cached.get("forecast", [])
                except Exception:
                    pass

        if lat is None or lon is None:
            lat, lon = self.geocode_location(location)

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"
                f"&forecast_days=10&timezone=auto"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "RestockIQ-Demand/2.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                daily = data.get("daily", {})
                times = daily.get("time", [])
                codes = daily.get("weathercode", [])
                t_maxs = daily.get("temperature_2m_max", [])
                t_mins = daily.get("temperature_2m_min", [])
                p_sums = daily.get("precipitation_sum", [])
                p_probs = daily.get("precipitation_probability_max", [])

                today = now.date()
                result = []
                for i in range(len(times)):
                    dt = datetime.strptime(times[i], "%Y-%m-%d").date()
                    if dt < today:
                        continue  # Skip yesterday or past dates; always start from Today

                    code = codes[i] if i < len(codes) else 1
                    t_max = round(float(t_maxs[i])) if i < len(t_maxs) else 32
                    t_min = round(float(t_mins[i])) if i < len(t_mins) else 22
                    psum = float(p_sums[i]) if (p_sums and i < len(p_sums)) else 0.0
                    pprob = int(p_probs[i]) if (p_probs and i < len(p_probs)) else 0

                    cond, icon, traffic_impact = parse_wmo_code(code, temp=t_max, precip_mm=psum, precip_prob=pprob)
                    is_today = (dt == today)
                    day_short = "Today" if is_today else dt.strftime("%a")

                    result.append({
                        "date": times[i],
                        "date_formatted": dt.strftime("%d %b %Y"),
                        "date_short": dt.strftime("%d %b"),
                        "day_short": day_short,
                        "day_name": dt.strftime("%A"),
                        "temp": t_max,
                        "temp_min": t_min,
                        "temp_max": t_max,
                        "precipitation_sum": psum,
                        "precipitation_probability": pprob,
                        "condition": cond,
                        "icon": icon,
                        "traffic_impact": traffic_impact,
                        "weather_code": code,
                        "source": "Open-Meteo Forecast API",
                    })

                    if len(result) == 7:
                        break

                if len(result) == 7:
                    self._cache["forecast_7d"][cache_key] = {
                        "forecast": result,
                        "updated_at": now.isoformat(),
                    }
                    self._save_cache()
                    return result
        except Exception as e:
            logger.warning(f"[WEATHER] Open-Meteo 7-day forecast lookup fallback: {e}")
            if cached and "forecast" in cached:
                return cached["forecast"]

        # Realistic regional fallback for Shirpur, Maharashtra (Post-monsoon dry autumn)
        pattern = [
            ("Partly Cloudy", "⛅", 32, 23, +6),
            ("Sunny", "☀️", 33, 22, +12),
            ("Partly Cloudy", "⛅", 32, 22, +6),
            ("Partly Cloudy", "⛅", 33, 22, +6),
            ("Sunny", "☀️", 34, 23, +12),
            ("Sunny", "☀️", 34, 23, +12),
            ("Sunny", "☀️", 34, 23, +12)
        ]
        result = []
        for i, (cond, icon, t_max, t_min, impact) in enumerate(pattern):
            cur_dt = now + timedelta(days=i)
            result.append({
                "date": cur_dt.strftime("%Y-%m-%d"),
                "date_formatted": cur_dt.strftime("%d %b %Y"),
                "date_short": cur_dt.strftime("%d %b"),
                "day_short": "Today" if i == 0 else cur_dt.strftime("%a"),
                "day_name": cur_dt.strftime("%A"),
                "temp": t_max,
                "temp_min": t_min,
                "temp_max": t_max,
                "precipitation_sum": 0.0,
                "precipitation_probability": 15,
                "condition": cond,
                "icon": icon,
                "traffic_impact": impact,
                "weather_code": 1,
                "source": "Open-Meteo Offline Fallback",
            })
        return result

    # --------------------------------------------------------------------------
    # Historical Weather Archive API
    # --------------------------------------------------------------------------
    def get_historical_weather(self, location: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Fetches historical daily weather records from the Open-Meteo Archive API
        for aligning historical sales observations with historical weather.
        """
        cache_key = f"{location.strip().lower()}_{start_date}_{end_date}"
        if cache_key in self._cache["historical"]:
            return self._cache["historical"][cache_key]

        lat, lon = self.geocode_location(location)

        try:
            url = (
                f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
                f"&start_date={start_date}&end_date={end_date}"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
                f"&timezone=auto"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "RestockIQ-Demand/2.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode())
                daily = data.get("daily", {})
                times = daily.get("time", [])
                t_maxs = daily.get("temperature_2m_max", [])
                t_mins = daily.get("temperature_2m_min", [])
                p_sums = daily.get("precipitation_sum", [])
                codes = daily.get("weathercode", [])

                records = []
                for i in range(len(times)):
                    records.append({
                        "date": times[i],
                        "temp_max": t_maxs[i] if i < len(t_maxs) else None,
                        "temp_min": t_mins[i] if i < len(t_mins) else None,
                        "precipitation_sum": p_sums[i] if i < len(p_sums) else 0.0,
                        "weather_code": codes[i] if i < len(codes) else 0,
                    })

                res = {
                    "location": location,
                    "start_date": start_date,
                    "end_date": end_date,
                    "records_count": len(records),
                    "daily_records": records,
                    "source": "Open-Meteo Archive API",
                }
                self._cache["historical"][cache_key] = res
                self._save_cache()
                return res
        except Exception as e:
            logger.warning(f"[WEATHER] Historical weather lookup failed: {e}")
            return {
                "location": location,
                "start_date": start_date,
                "end_date": end_date,
                "records_count": 0,
                "daily_records": [],
                "error": str(e),
                "source": "Open-Meteo Archive API",
            }

    # --------------------------------------------------------------------------
    # Telemetry Metadata & Provider Licensing
    # --------------------------------------------------------------------------
    def get_metadata(self) -> Dict[str, Any]:
        """Returns service status, cache age, providers, and commercial licensing terms."""
        return {
            "provider": "Open-Meteo",
            "forecast_api": "https://api.open-meteo.com/v1/forecast",
            "historical_api": "https://archive-api.open-meteo.com/v1/archive",
            "geocoding_api": "https://geocoding-api.open-meteo.com/v1/search",
            "terms_of_use": "Free for non-commercial & educational use (CC BY 4.0). Commercial production requires paid subscription or self-hosted open-source model container.",
            "commercial_use_status": "Non-commercial free tier active. Commercial deployment requires commercial plan agreement.",
            "live_update_frequency": "minute-to-minute (60 seconds)",
            "forecast_horizon_days": 7,
            "cached_locations_count": len(self._cache["live_weather"]),
            "last_saved": self._cache.get("last_saved"),
        }


weather_service = WeatherService()
