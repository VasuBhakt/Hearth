"""
Hearth Centralized Configuration
Loads and validates settings from environment variables (.env).
Provides minimal, essential defaults for server, database, preferences, travel, and weather.
"""
import os
import json
from typing import List, Optional

import sys

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# Ensure both 'config' and 'server.config' reference this module in sys.modules
if __name__ in sys.modules:
    sys.modules["config"] = sys.modules[__name__]
    sys.modules["server.config"] = sys.modules[__name__]


def parse_env_list(val: Optional[str], default: Optional[List[str]] = None) -> List[str]:
    """Parses a comma-separated string or JSON array from an env variable into a list of strings."""
    if not val:
        return list(default or [])
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in val.split(",") if item.strip()]


def parse_env_float(val: Optional[str], default: float) -> float:
    try:
        return float(val.strip().strip('"').strip("'")) if val else default
    except (ValueError, AttributeError):
        return default


def parse_env_int(val: Optional[str], default: int) -> int:
    try:
        return int(val.strip().strip('"').strip("'")) if val else default
    except (ValueError, AttributeError):
        return default


def parse_env_str(val: Optional[str], default: str) -> str:
    return val.strip().strip('"').strip("'") if val else default


# ============================================================================
# 1. Server & Database
# ============================================================================
PORT = parse_env_int(os.environ.get("PORT"), 8000)
HOST = parse_env_str(os.environ.get("HOST"), "127.0.0.1")
MIN_PROTOCOL_VERSION = parse_env_str(os.environ.get("MIN_PROTOCOL_VERSION"), "2025-11-25")
HEARTH_DB_PATH = parse_env_str(os.environ.get("HEARTH_DB_PATH"), "hearth.db")

# ============================================================================
# 2. Family Preferences & Defaults (Configurable via .env)
# ============================================================================
DEFAULT_HOME_NAME = parse_env_str(os.environ.get("DEFAULT_HOME_NAME"), "Home")
DEFAULT_HOME_LATITUDE = parse_env_float(os.environ.get("DEFAULT_HOME_LATITUDE"), 40.6782)
DEFAULT_HOME_LONGITUDE = parse_env_float(os.environ.get("DEFAULT_HOME_LONGITUDE"), -73.9442)
DEFAULT_ARRIVAL_BUFFER_MINUTES = parse_env_int(os.environ.get("DEFAULT_ARRIVAL_BUFFER_MINUTES"), 30)

# Default packing & snack list from .env
DEFAULT_SAVED_SNACKS = parse_env_list(
    os.environ.get("DEFAULT_SAVED_SNACKS"),
    ["Orange slices", "Granola bars", "Electrolyte drinks", "Ice pack"],
)

# Scheduling Window (Candidate hours for rescheduling)
SCHEDULE_START_HOUR = parse_env_int(os.environ.get("SCHEDULE_START_HOUR"), 9)
SCHEDULE_END_HOUR = parse_env_int(os.environ.get("SCHEDULE_END_HOUR"), 17)

# ============================================================================
# 3. Travel & Weather Engine Defaults
# ============================================================================
DEFAULT_DRIVE_SPEED_KMH = parse_env_float(os.environ.get("DEFAULT_DRIVE_SPEED_KMH"), 45.0)
DEFAULT_TRAFFIC_BUFFER_MINUTES = parse_env_int(os.environ.get("DEFAULT_TRAFFIC_BUFFER_MINUTES"), 10)

OPEN_METEO_API_URL = parse_env_str(os.environ.get("OPEN_METEO_API_URL"), "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_DAILY_METRICS = parse_env_str(
    os.environ.get("OPEN_METEO_DAILY_METRICS"),
    "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
)
OPEN_METEO_TIMEZONE = parse_env_str(os.environ.get("OPEN_METEO_TIMEZONE"), "auto")
OPEN_METEO_TIMEOUT_SECONDS = parse_env_float(os.environ.get("OPEN_METEO_TIMEOUT_SECONDS"), 4.0)

WEATHER_RAIN_THRESHOLD_PERCENT = parse_env_float(os.environ.get("WEATHER_RAIN_THRESHOLD_PERCENT"), 40.0)
WEATHER_COLD_THRESHOLD_C = parse_env_float(os.environ.get("WEATHER_COLD_THRESHOLD_C"), 12.0)
WEATHER_HOT_THRESHOLD_C = parse_env_float(os.environ.get("WEATHER_HOT_THRESHOLD_C"), 28.0)

# ============================================================================
# 4. Generic Matching Lists & Keywords (Configurable via .env)
# ============================================================================
LOCATION_KEYWORD_MATCHES = parse_env_list(
    os.environ.get("LOCATION_KEYWORD_MATCHES"),
    ["home", "origin", "base", "start", "dep"],
)
PACKING_KEYWORD_MATCHES = parse_env_list(
    os.environ.get("PACKING_KEYWORD_MATCHES"),
    ["snack", "pack", "gear", "item", "check", "suppl", "food"],
)
EVENT_TEXT_FIELDS = parse_env_list(
    os.environ.get("EVENT_TEXT_FIELDS"),
    ["title", "description", "category", "summary", "notes"],
)
BUFFER_KEYWORD_MATCHES = parse_env_list(
    os.environ.get("BUFFER_KEYWORD_MATCHES"),
    ["buffer"],
)
RAIN_WEATHER_KEYWORDS = parse_env_list(
    os.environ.get("RAIN_WEATHER_KEYWORDS"),
    ["rain", "storm", "drizzle", "shower"],
)
COLD_WEATHER_KEYWORDS = parse_env_list(
    os.environ.get("COLD_WEATHER_KEYWORDS"),
    ["cold", "snow", "ice", "freeze", "chill"],
)
HOT_WEATHER_KEYWORDS = parse_env_list(
    os.environ.get("HOT_WEATHER_KEYWORDS"),
    ["hot", "sunny", "heat"],
)
