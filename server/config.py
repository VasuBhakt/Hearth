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


def parse_env_bool(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    v = val.strip().strip('"').strip("'").lower()
    if v in ("true", "1", "yes", "y", "on"):
        return True
    if v in ("false", "0", "no", "n", "off"):
        return False
    return default


# ============================================================================
# 1. Server & Database
# ============================================================================
PORT = parse_env_int(os.environ.get("PORT"), 8000)
HOST = parse_env_str(os.environ.get("HOST"), "127.0.0.1")
MIN_PROTOCOL_VERSION = parse_env_str(os.environ.get("MIN_PROTOCOL_VERSION"), "2025-11-25")
CURRENT_PROTOCOL_VERSION = parse_env_str(os.environ.get("CURRENT_PROTOCOL_VERSION"), "2026-07-28")
HEARTH_DB_PATH = parse_env_str(os.environ.get("HEARTH_DB_PATH"), "hearth.db")
MCP_SERVER_NAME = parse_env_str(os.environ.get("MCP_SERVER_NAME"), "hearth-server")
MCP_SERVER_VERSION = parse_env_str(os.environ.get("MCP_SERVER_VERSION"), "0.1.0")

# ============================================================================
# 2. Family Preferences & Defaults (Configurable via .env)
# ============================================================================
DEFAULT_HOME_NAME = parse_env_str(os.environ.get("DEFAULT_HOME_NAME"), "Home")
DEFAULT_HOME_LATITUDE = parse_env_float(os.environ.get("DEFAULT_HOME_LATITUDE"), 40.6782)
DEFAULT_HOME_LONGITUDE = parse_env_float(os.environ.get("DEFAULT_HOME_LONGITUDE"), -73.9442)
DEFAULT_ARRIVAL_BUFFER_MINUTES = parse_env_int(os.environ.get("DEFAULT_ARRIVAL_BUFFER_MINUTES"), 30)

DEFAULT_EVENT_DURATION_HOURS = parse_env_float(os.environ.get("DEFAULT_EVENT_DURATION_HOURS"), 2.0)
DEFAULT_TARGET_DATE = parse_env_str(os.environ.get("DEFAULT_TARGET_DATE"), "2026-10-17")
DEFAULT_TARGET_TIME = parse_env_str(os.environ.get("DEFAULT_TARGET_TIME"), "09:00:00")
DEFAULT_ARRIVAL_DATETIME = parse_env_str(
    os.environ.get("DEFAULT_ARRIVAL_DATETIME"),
    f"{DEFAULT_TARGET_DATE}T{DEFAULT_TARGET_TIME}",
)

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
MIN_DRIVE_TIME_MINUTES = parse_env_int(os.environ.get("MIN_DRIVE_TIME_MINUTES"), 10)

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

FALLBACK_WEATHER_TEMP_C = parse_env_float(os.environ.get("FALLBACK_WEATHER_TEMP_C"), 16.5)
FALLBACK_WEATHER_CONDITION = parse_env_str(os.environ.get("FALLBACK_WEATHER_CONDITION"), "Light Rain / Showers")
FALLBACK_WEATHER_PRECIP_PERCENT = parse_env_float(os.environ.get("FALLBACK_WEATHER_PRECIP_PERCENT"), 75.0)
FALLBACK_WEATHER_WIND_KPH = parse_env_float(os.environ.get("FALLBACK_WEATHER_WIND_KPH"), 22.0)
FALLBACK_WEATHER_RAIN_WARNING = parse_env_bool(os.environ.get("FALLBACK_WEATHER_RAIN_WARNING"), True)

# ============================================================================
# 4. Generic Matching Lists & Keywords (Configurable via .env)
# ============================================================================
LOCATION_KEYWORD_MATCHES = parse_env_list(
    os.environ.get("LOCATION_KEYWORD_MATCHES"),
    ["home", "origin", "base", "start", "dep"],
)
PACKING_KEYWORD_MATCHES = parse_env_list(
    os.environ.get("PACKING_KEYWORD_MATCHES"),
    ["snack", "pack", "gear", "item", "check", "suppl", "food", "chair", "towel", "water", "umbrella"],
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

# ============================================================================
# 5. Security, Approval Gate & Undo Defaults (Configurable via .env)
# ============================================================================
APPROVAL_TOKEN_TTL_MINUTES = parse_env_int(os.environ.get("APPROVAL_TOKEN_TTL_MINUTES"), 15)
APPROVAL_TOKEN_LENGTH_BYTES = parse_env_int(os.environ.get("APPROVAL_TOKEN_LENGTH_BYTES"), 32)
UNDO_LEDGER_MAX_ENTRIES = parse_env_int(os.environ.get("UNDO_LEDGER_MAX_ENTRIES"), 50)
DEFAULT_PLAN_STATUS_DRAFT = parse_env_str(os.environ.get("DEFAULT_PLAN_STATUS_DRAFT"), "draft")
DEFAULT_PLAN_STATUS_COMMITTED = parse_env_str(os.environ.get("DEFAULT_PLAN_STATUS_COMMITTED"), "committed")
ACTION_TYPE_COMMIT_PLAN = parse_env_str(os.environ.get("ACTION_TYPE_COMMIT_PLAN"), "commit_plan")
ACTION_TYPE_RESCHEDULE = parse_env_str(os.environ.get("ACTION_TYPE_RESCHEDULE"), "reschedule_event")
ACTION_TYPE_DELETE_EVENT = parse_env_str(os.environ.get("ACTION_TYPE_DELETE_EVENT"), "delete_event")
MAX_SLOT_SEARCH_DAYS = parse_env_int(os.environ.get("MAX_SLOT_SEARCH_DAYS"), 14)
DEFAULT_SLOT_SEARCH_HOUR = parse_env_int(os.environ.get("DEFAULT_SLOT_SEARCH_HOUR"), 10)
WEEKDAY_WORKDAY_MAX = parse_env_int(os.environ.get("WEEKDAY_WORKDAY_MAX"), 5)
# Max user+assistant turns kept in memory per session (each turn = 2 messages)
CONVERSATION_HISTORY_MAX_TURNS = parse_env_int(os.environ.get("CONVERSATION_HISTORY_MAX_TURNS"), 20)

# ============================================================================
# 6. Assistant Simulator Web UI Settings (Configurable via .env)
# ============================================================================
SIMULATOR_PORT = parse_env_int(os.environ.get("SIMULATOR_PORT"), 8080)
SIMULATOR_HOST = parse_env_str(os.environ.get("SIMULATOR_HOST"), "127.0.0.1")
DEFAULT_DEMO_SCENARIO_PROMPT = parse_env_str(
    os.environ.get("DEFAULT_DEMO_SCENARIO_PROMPT"),
    "Get us ready for Saturday's tournament",
)
SIMULATOR_TITLE = parse_env_str(
    os.environ.get("SIMULATOR_TITLE"),
    "Hearth Family Assistant",
)

# ============================================================================
# 7. AI Agent / LLM Settings (Configurable via .env)
# ============================================================================
LLM_PROVIDER = parse_env_str(os.environ.get("LLM_PROVIDER"), "groq")
GROQ_API_URL = parse_env_str(os.environ.get("GROQ_API_URL"), "https://api.groq.com/openai/v1/chat/completions")
GROQ_API_KEY = parse_env_str(os.environ.get("GROQ_API_KEY"), "")
GROQ_MODEL = parse_env_str(os.environ.get("GROQ_MODEL"), "openai/gpt-oss-120b")
GROQ_TEMPERATURE = parse_env_float(os.environ.get("GROQ_TEMPERATURE"), 0.2)
GROQ_TIMEOUT_SECONDS = parse_env_float(os.environ.get("GROQ_TIMEOUT_SECONDS"), 30.0)

OLLAMA_BASE_URL = parse_env_str(os.environ.get("OLLAMA_BASE_URL"), "http://127.0.0.1:11434")
OLLAMA_MODEL = parse_env_str(os.environ.get("OLLAMA_MODEL"), "llama3.2")
OLLAMA_TIMEOUT_SECONDS = parse_env_float(os.environ.get("OLLAMA_TIMEOUT_SECONDS"), 90.0)

AWS_REGION = parse_env_str(os.environ.get("AWS_REGION"), "us-east-1")
AWS_BEDROCK_MODEL = parse_env_str(os.environ.get("AWS_BEDROCK_MODEL"), "amazon.nova-lite-v1:0")

# ============================================================================
# 8. Router Keywords & Natural Language Signals (Configurable via .env)
# ============================================================================
DEFAULT_VENUE_NAME = parse_env_str(os.environ.get("DEFAULT_VENUE_NAME"), "City Sports Complex")
DEFAULT_VENUE_LATITUDE = parse_env_float(os.environ.get("DEFAULT_VENUE_LATITUDE"), 40.7128)
DEFAULT_VENUE_LONGITUDE = parse_env_float(os.environ.get("DEFAULT_VENUE_LONGITUDE"), -74.0060)

PLAN_CANCEL_KEYWORDS = parse_env_list(
    os.environ.get("PLAN_CANCEL_KEYWORDS"),
    [
        "cancel plan",
        "cancel the plan",
        "cancel this plan",
        "remove plan",
        "remove the plan",
        "remove this plan",
        "delete plan",
        "delete the plan",
        "delete this plan",
        "clear plan",
        "clear the plan",
        "discard plan",
        "discard the plan",
        "drop plan",
        "drop the plan",
        "dismiss plan",
        "dismiss the plan",
        "forget plan",
        "forget the plan",
        "start over",
        "remove card",
        "cancel card",
    ],
)

GREETING_KEYWORDS = parse_env_list(
    os.environ.get("GREETING_KEYWORDS"),
    ["hi", "hello", "hey", "help", "who are you", "what can you do"],
)

ADD_EVENT_KEYWORDS = parse_env_list(
    os.environ.get("ADD_EVENT_KEYWORDS"),
    ["add event", "add another event", "create event", "new event", "schedule event"],
)

DELETE_EVENT_KEYWORDS = parse_env_list(
    os.environ.get("DELETE_EVENT_KEYWORDS"),
    ["remove event", "remove the event", "delete event", "delete the event", "cancel event", "cancel the event", "drop event"],
)

REVISION_KEYWORDS = parse_env_list(
    os.environ.get("REVISION_KEYWORDS"),
    ["move", "reschedule", "shift", "pack", "leave", "earlier", "later", "add to packing"],
)

SCHEDULE_KEYWORDS = parse_env_list(
    os.environ.get("SCHEDULE_KEYWORDS"),
    ["schedule", "events", "calendar", "agenda", "what's on", "what is on", "what do we have"],
)

PLANNING_SIGNALS = parse_env_list(
    os.environ.get("PLANNING_SIGNALS"),
    ["tournament", "saturday", "weekend", "prepare", "ready", "plan", "organize", "what should we do", "get us ready", "upcoming", "fix", "resolve"],
)

CONFLICT_KEYWORDS = parse_env_list(
    os.environ.get("CONFLICT_KEYWORDS"),
    ["conflict", "clash", "overlap"],
)

WEATHER_KEYWORDS = parse_env_list(
    os.environ.get("WEATHER_KEYWORDS"),
    ["weather", "rain", "forecast", "temperature", "umbrella"],
)




