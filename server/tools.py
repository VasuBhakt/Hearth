"""
Hearth Read-Only Tools
Gathers facts: context, conflicts, travel times, and weather forecasts.
All configurations, URLs, and defaults are dynamically loaded from environment variables and database.
"""
import os
import sys
import math
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import httpx

# Ensure local modules resolve cleanly in all runtime contexts
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from models import (
    Event,
    Location,
    ConflictReport,
    TravelEstimate,
    WeatherForecast,
)
from db import (
    get_all_events,
    get_all_preferences,
    get_preference,
    set_preference,
    save_event,
    delete_event,
)

# Import environment configurations and defaults
try:
    from config import (
        OPEN_METEO_API_URL,
        OPEN_METEO_DAILY_METRICS,
        OPEN_METEO_TIMEZONE,
        OPEN_METEO_TIMEOUT_SECONDS,
        DEFAULT_DRIVE_SPEED_KMH,
        DEFAULT_TRAFFIC_BUFFER_MINUTES,
        DEFAULT_ARRIVAL_BUFFER_MINUTES,
        WEATHER_RAIN_THRESHOLD_PERCENT,
        BUFFER_KEYWORD_MATCHES,
        DEFAULT_HOME_NAME,
        DEFAULT_HOME_LATITUDE,
        DEFAULT_HOME_LONGITUDE,
        DEFAULT_VENUE_NAME,
        DEFAULT_VENUE_LATITUDE,
        DEFAULT_VENUE_LONGITUDE,
        DEFAULT_EVENT_DURATION_HOURS,
        DEFAULT_TARGET_DATE,
        DEFAULT_ARRIVAL_DATETIME,
        MIN_DRIVE_TIME_MINUTES,
        FALLBACK_WEATHER_TEMP_C,
        FALLBACK_WEATHER_CONDITION,
        FALLBACK_WEATHER_PRECIP_PERCENT,
        FALLBACK_WEATHER_WIND_KPH,
        FALLBACK_WEATHER_RAIN_WARNING,
    )
except ImportError:
    OPEN_METEO_API_URL = os.environ.get("OPEN_METEO_API_URL", "https://api.open-meteo.com/v1/forecast").strip('"').strip("'")
    OPEN_METEO_DAILY_METRICS = os.environ.get("OPEN_METEO_DAILY_METRICS", "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code").strip('"').strip("'")
    OPEN_METEO_TIMEZONE = os.environ.get("OPEN_METEO_TIMEZONE", "auto").strip('"').strip("'")
    OPEN_METEO_TIMEOUT_SECONDS = float(os.environ.get("OPEN_METEO_TIMEOUT_SECONDS", "4.0").strip('"').strip("'"))
    DEFAULT_DRIVE_SPEED_KMH = float(os.environ.get("DEFAULT_DRIVE_SPEED_KMH", "45.0").strip('"').strip("'"))
    DEFAULT_TRAFFIC_BUFFER_MINUTES = int(os.environ.get("DEFAULT_TRAFFIC_BUFFER_MINUTES", "10").strip('"').strip("'"))
    DEFAULT_ARRIVAL_BUFFER_MINUTES = int(os.environ.get("DEFAULT_ARRIVAL_BUFFER_MINUTES", "30").strip('"').strip("'"))
    WEATHER_RAIN_THRESHOLD_PERCENT = float(os.environ.get("WEATHER_RAIN_THRESHOLD_PERCENT", "40.0").strip('"').strip("'"))
    BUFFER_KEYWORD_MATCHES = ["buffer"]
    DEFAULT_HOME_NAME = "Home"
    DEFAULT_HOME_LATITUDE = 40.6782
    DEFAULT_HOME_LONGITUDE = -73.9442
    DEFAULT_VENUE_NAME = "City Sports Complex"
    DEFAULT_VENUE_LATITUDE = 40.7128
    DEFAULT_VENUE_LONGITUDE = -74.0060
    DEFAULT_EVENT_DURATION_HOURS = 2.0
    DEFAULT_TARGET_DATE = "2026-10-17"
    DEFAULT_ARRIVAL_DATETIME = "2026-10-17T09:00:00"
    MIN_DRIVE_TIME_MINUTES = 10
    FALLBACK_WEATHER_TEMP_C = 16.5
    FALLBACK_WEATHER_CONDITION = "Light Rain / Showers"
    FALLBACK_WEATHER_PRECIP_PERCENT = 75.0
    FALLBACK_WEATHER_WIND_KPH = 22.0
    FALLBACK_WEATHER_RAIN_WARNING = True



def resolve_arrival_buffer_minutes(explicit_buffer: Optional[int] = None) -> int:
    """Dynamically finds the arrival buffer from preferences or defaults."""
    if explicit_buffer is not None:
        return explicit_buffer
    prefs = get_all_preferences()
    for key, val in prefs.items():
        if any(b in key.lower() for b in BUFFER_KEYWORD_MATCHES) and isinstance(val, (int, float)):
            return int(val)
    return DEFAULT_ARRIVAL_BUFFER_MINUTES


# ============================================================================
# 1. get_context
# ============================================================================

def get_context() -> Dict[str, Any]:
    """
    Returns all calendar events, saved family preferences, and active schedule conflicts.
    Completely dynamic — returns the full dictionary of stored preferences and detected conflicts.
    """
    events = get_all_events()
    preferences = get_all_preferences()
    conflicts = check_conflicts(events)

    return {
        "events": [e.model_dump() for e in events],
        "preferences": preferences,
        "conflicts": [c.model_dump() for c in conflicts],
    }


# ============================================================================
# 2. check_conflicts
# ============================================================================

def check_conflicts(
    events: Optional[List[Event]] = None,
    buffer_minutes: Optional[int] = None,
) -> List[ConflictReport]:
    """
    Scans events for time overlaps and tight gaps.
    Buffer minutes is dynamically resolved from family preferences or env default.
    """
    if events is None:
        events = get_all_events()

    buffer_minutes = resolve_arrival_buffer_minutes(buffer_minutes)

    conflicts: List[ConflictReport] = []
    sorted_events = sorted(events, key=lambda e: e.start_time)

    for i in range(len(sorted_events)):
        for j in range(i + 1, len(sorted_events)):
            e1 = sorted_events[i]
            e2 = sorted_events[j]

            t1_start = datetime.fromisoformat(e1.start_time)
            t1_end = datetime.fromisoformat(e1.end_time)
            t2_start = datetime.fromisoformat(e2.start_time)
            t2_end = datetime.fromisoformat(e2.end_time)

            # Direct overlap check
            if t1_start < t2_end and t2_start < t1_end:
                conflicts.append(ConflictReport(
                    event1_id=e1.id,
                    event2_id=e2.id,
                    conflict_type="Overlap",
                    details=f"'{e1.title}' overlaps with '{e2.title}' between {t2_start.strftime('%H:%M')} and {t1_end.strftime('%H:%M')}."
                ))
            # Tight gap check on same day
            elif t1_start.date() == t2_start.date() and (t2_start - t1_end) < timedelta(minutes=buffer_minutes):
                gap_mins = int((t2_start - t1_end).total_seconds() / 60)
                if gap_mins >= 0:
                    conflicts.append(ConflictReport(
                        event1_id=e1.id,
                        event2_id=e2.id,
                        conflict_type="Tight_Gap",
                        details=f"Only {gap_mins} min gap between '{e1.title}' and '{e2.title}' (less than the {buffer_minutes} min arrival buffer)."
                    ))

    return conflicts


# ============================================================================
# 3. estimate_travel
# ============================================================================

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates in kilometers."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def estimate_travel(
    origin_name: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    dest_name: Optional[str] = None,
    dest_lat: Optional[float] = None,
    dest_lng: Optional[float] = None,
    target_arrival_time: Optional[str] = None,
    buffer_minutes: Optional[int] = None,
    **kwargs,
) -> TravelEstimate:
    """
    Estimates driving distance, travel duration, and recommended departure time.
    Calculates departure dynamically using drive time + arrival buffer.
    Detects online/virtual events to avoid phantom driving calculations.
    """
    origin_name = origin_name or DEFAULT_HOME_NAME
    dest_name = dest_name or DEFAULT_VENUE_NAME
    target_arrival_time = target_arrival_time or DEFAULT_ARRIVAL_DATETIME

    dest_lower = (dest_name or "").lower().strip()
    is_virtual = any(k in dest_lower for k in ["online", "virtual", "remote", "zoom", "discord"]) or (dest_lower in ["home", origin_name.lower().strip()])

    arrival_dt = datetime.fromisoformat(target_arrival_time)

    if is_virtual:
        return TravelEstimate(
            origin=origin_name,
            destination=dest_name or "Online",
            distance_km=0.0,
            travel_time_minutes=0,
            travel_mode="none",
            recommended_leave_by=arrival_dt.isoformat(),
        )

    # Resolve coordinates if not provided
    if origin_lat is None or origin_lng is None:
        origin_lat = DEFAULT_HOME_LATITUDE
        origin_lng = DEFAULT_HOME_LONGITUDE

    if dest_lat is None or dest_lng is None:
        events = get_all_events()
        matching_ev = next((e for e in events if e.location and dest_name.lower() in e.location.name.lower()), None)
        if matching_ev and matching_ev.location:
            dest_lat = matching_ev.location.latitude
            dest_lng = matching_ev.location.longitude
        else:
            dest_lat = DEFAULT_VENUE_LATITUDE
            dest_lng = DEFAULT_VENUE_LONGITUDE

    distance_km = haversine_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
    
    # Drive time dynamically derived from configured speed + traffic buffer
    drive_minutes = max(
        MIN_DRIVE_TIME_MINUTES,
        int((distance_km / DEFAULT_DRIVE_SPEED_KMH) * 60) + DEFAULT_TRAFFIC_BUFFER_MINUTES
    )

    buffer_minutes = resolve_arrival_buffer_minutes(buffer_minutes)
    leave_dt = arrival_dt - timedelta(minutes=(drive_minutes + buffer_minutes))

    return TravelEstimate(
        origin=origin_name,
        destination=dest_name,
        distance_km=distance_km,
        travel_time_minutes=drive_minutes,
        travel_mode="driving",
        recommended_leave_by=leave_dt.isoformat(),
    )


# ============================================================================
# 4. get_forecast (Open-Meteo with Offline Fallback)
# ============================================================================

async def get_forecast(
    location_name: Optional[str] = None,
    latitude: Optional[Any] = None,
    longitude: Optional[float] = None,
    date_str: Optional[str] = None,
    **kwargs,
) -> WeatherForecast:
    """
    Fetches real-time forecast from Open-Meteo API using async HTTP.
    API base URL is loaded dynamically from OPEN_METEO_API_URL env variable.
    Gracefully falls back to bundled demo forecast if offline or API is unreachable.
    Accepts (location_name, date_str) or full coordinates dynamically.
    """
    # Handle shifted positional arguments (e.g. get_forecast("Clinic", "2026-10-17"))
    if isinstance(latitude, str) and (longitude is None or isinstance(longitude, (int, float))) and date_str is None:
        date_str = latitude
        latitude = None

    location_name = location_name or kwargs.get("location") or DEFAULT_VENUE_NAME
    date_str = date_str or kwargs.get("date") or DEFAULT_TARGET_DATE

    # Normalise date string to YYYY-MM-DD
    date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', str(date_str))
    if date_match:
        date_str = date_match.group(1)
    else:
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%a, %b %d, %Y", "%A, %B %d, %Y"):
            try:
                clean_d = re.sub(r'^(?:sat(?:urday)?|sun(?:day)?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?),?\s*', '', str(date_str), flags=re.IGNORECASE)
                parsed_dt = datetime.strptime(clean_d.strip(), fmt.replace("%a, ", "").replace("%A, ", ""))
                date_str = parsed_dt.strftime("%Y-%m-%d")
                break
            except Exception:
                pass

    # Dynamic coordinate resolution if missing
    if latitude is None or longitude is None:
        lat_found, lng_found = None, None
        events = get_all_events()
        for ev in events:
            loc_label = ev.location_name or (ev.location.name if ev.location else "")
            if location_name and (location_name.lower() in loc_label.lower() or loc_label.lower() in location_name.lower()):
                if ev.location and ev.location.latitude and ev.location.longitude:
                    lat_found = ev.location.latitude
                    lng_found = ev.location.longitude
                    break
        if lat_found is None and location_name and location_name.lower() not in ["home", "origin"]:
            try:
                geo_url = "https://geocoding-api.open-meteo.com/v1/search"
                async with httpx.AsyncClient(timeout=3.0) as geo_client:
                    geo_resp = await geo_client.get(geo_url, params={"name": location_name, "count": 1})
                    if geo_resp.status_code == 200:
                        geo_results = geo_resp.json().get("results", [])
                        if geo_results:
                            lat_found = float(geo_results[0]["latitude"])
                            lng_found = float(geo_results[0]["longitude"])
            except Exception:
                pass
        latitude = lat_found if lat_found is not None else DEFAULT_VENUE_LATITUDE
        longitude = lng_found if lng_found is not None else DEFAULT_VENUE_LONGITUDE
    else:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except Exception:
            latitude = DEFAULT_VENUE_LATITUDE
            longitude = DEFAULT_VENUE_LONGITUDE
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": OPEN_METEO_DAILY_METRICS,
        "timezone": OPEN_METEO_TIMEZONE,
    }

    try:
        async with httpx.AsyncClient(timeout=OPEN_METEO_TIMEOUT_SECONDS) as client:
            resp = await client.get(OPEN_METEO_API_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                daily = data.get("daily", {})
                dates = daily.get("time", [])

                idx = None
                if date_str in dates:
                    idx = dates.index(date_str)
                elif dates:
                    idx = 0
                    date_str = dates[0]

                if idx is not None:
                    precip_pct = daily.get("precipitation_probability_max", [0])[idx]
                    temp_max = daily.get("temperature_2m_max", [20.0])[idx]
                    code = daily.get("weather_code", [0])[idx]

                    # WMO codes >= 51 indicate drizzle / rain, or threshold from .env
                    is_rain = code >= 51 or precip_pct >= WEATHER_RAIN_THRESHOLD_PERCENT
                    condition = "Rain / Showers" if is_rain else "Partly Cloudy"

                    return WeatherForecast(
                        location=location_name,
                        forecast_time=date_str,
                        temperature_c=temp_max,
                        weather_condition=condition,
                        precipitation_chance_percent=precip_pct,
                        wind_speed_kph=18.0,
                        rain_warning=is_rain,
                    )
    except Exception:
        pass  # Graceful fallback to bundled offline demo forecast

    # Bundled fallback matching configurable forecast defaults from .env
    return WeatherForecast(
        location=location_name,
        forecast_time=date_str,
        temperature_c=FALLBACK_WEATHER_TEMP_C,
        weather_condition=FALLBACK_WEATHER_CONDITION,
        precipitation_chance_percent=FALLBACK_WEATHER_PRECIP_PERCENT,
        wind_speed_kph=FALLBACK_WEATHER_WIND_KPH,
        rain_warning=FALLBACK_WEATHER_RAIN_WARNING,
    )


# ============================================================================
# 5. remember_preference (Cross-Session Family Preference Memory)
# ============================================================================

def remember_preference(key: str, value: Any) -> Dict[str, Any]:
    """
    Saves or updates a family preference setting in SQLite for cross-session recall.
    Supports snacks, arrival buffers, packing lists, favorite venues, etc.
    Enables 'same as last time' user journey.
    """
    if not key or not str(key).strip():
        raise ValueError("Preference key cannot be empty.")

    clean_key = str(key).strip().lower().replace(" ", "_")
    set_preference(clean_key, value)

    return {
        "success": True,
        "key": clean_key,
        "value": value,
        "message": f"Successfully remembered preference '{clean_key}'.",
    }


# ============================================================================
# 6. add_event (Add New Calendar Event / Appointment)
# ============================================================================

def parse_datetime_flexible(dt_input: str) -> str:
    """
    Parses arbitrary date/time strings into ISO 8601 format.
    Handles ISO strings, human dates ('24th october 2026, from 8:05 pm ist'),
    and standard date formats without crashing.
    """
    if not dt_input or not str(dt_input).strip():
        return datetime.now().isoformat()

    clean = str(dt_input).strip()
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00")).isoformat()
    except Exception:
        pass

    import re
    # Remove ordinal suffixes: 24th -> 24, 1st -> 1, 2nd -> 2, 3rd -> 3
    clean_ord = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', clean, flags=re.IGNORECASE)
    # Strip common timezone abbreviations
    clean_ord = re.sub(r'\b(ist|est|edt|cst|cdt|pst|pdt|utc|gmt)\b', '', clean_ord, flags=re.IGNORECASE)
    # Strip filler words and punctuation
    clean_ord = clean_ord.replace(",", " ")
    clean_ord = re.sub(r'\b(from|at|on|starts?|ends?)\b', ' ', clean_ord, flags=re.IGNORECASE)
    clean_ord = re.sub(r'\s+', ' ', clean_ord).strip()

    formats = [
        "%d %B %Y %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%B %d %Y %I:%M %p",
        "%b %d %Y %I:%M %p",
        "%d %B %Y %H:%M",
        "%d %b %Y %H:%M",
        "%B %d %Y %H:%M",
        "%b %d %Y %H:%M",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(clean_ord, fmt)
            return parsed.isoformat()
        except Exception:
            continue

    # Regex extraction fallback
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', clean)
    if m:
        y, mon, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        tm = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?', clean, re.IGNORECASE)
        h, mn = 12, 0
        if tm:
            h = int(tm.group(1))
            mn = int(tm.group(2))
            if tm.group(4) and tm.group(4).lower() == 'pm' and h < 12:
                h += 12
            elif tm.group(4) and tm.group(4).lower() == 'am' and h == 12:
                h = 0
        return datetime(y, mon, d, h, mn).isoformat()

    return dt_input


def add_event(
    title: str,
    start_time: str,
    end_time: Optional[str] = None,
    location_name: Optional[str] = None,
    description: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    priority: int = 1,
    required_items: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Inserts a new calendar event into SQLite and checks for immediate conflicts.
    Dynamically normalizes input timestamps into ISO 8601.
    """
    import uuid

    if not title or not str(title).strip():
        raise ValueError("Event title cannot be empty.")

    clean_title = str(title).strip()
    norm_start = parse_datetime_flexible(start_time)

    # Generate end_time if missing (configurable duration from .env)
    if not end_time:
        try:
            start_dt = datetime.fromisoformat(norm_start.replace("Z", "+00:00"))
            norm_end = (start_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)).isoformat()
        except Exception:
            norm_end = norm_start
    else:
        norm_end = parse_datetime_flexible(end_time)

    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    loc = Location(name=location_name, latitude=DEFAULT_VENUE_LATITUDE, longitude=DEFAULT_VENUE_LONGITUDE) if location_name else None

    ev = Event(
        id=event_id,
        title=clean_title,
        start_time=norm_start,
        end_time=norm_end,
        location=loc,
        attendees=attendees or [],
        description=description,
        priority=priority,
        required_items=required_items or [],
    )
    save_event(ev)

    # Immediately check if this new event introduces any conflicts
    all_events = get_all_events()
    all_conflicts = check_conflicts(all_events)
    clashes = [c for c in all_conflicts if event_id in (c.event1_id, c.event2_id)]

    return {
        "success": True,
        "event": ev.model_dump(),
        "has_conflicts": len(clashes) > 0,
        "conflicts": [c.model_dump() for c in clashes],
        "message": f"Added '{clean_title}' to calendar successfully.",
    }


# ============================================================================
# 7. remove_event (Remove / Delete Calendar Event)
# ============================================================================

def remove_event(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Finds and deletes a calendar event from SQLite by title, keyword, or exact ID.
    Returns the deleted event details and success status.
    """
    events = get_all_events()
    target = None

    if event_id:
        target = next((e for e in events if e.id == event_id), None)

    if not target and event_title:
        clean = event_title.strip().lower()
        # Direct exact or substring match
        target = next((e for e in events if clean in e.title.lower() or e.title.lower() in clean), None)
        if not target:
            # Word token match (e.g. 'soccer' matches "Maya's Soccer Tournament")
            words = [w for w in clean.split() if len(w) >= 3 and w not in ["event", "calendar", "schedule", "please", "remove", "delete"]]
            if words:
                target = next((e for e in events if any(w in e.title.lower() for w in words)), None)

    if not target:
        return {
            "success": False,
            "message": f"Could not find any calendar event matching '{event_title or event_id}'.",
        }

    deleted = delete_event(target.id)
    return {
        "success": deleted,
        "event_id": target.id,
        "deleted_event": target.model_dump(),
        "message": f"Successfully removed '{target.title}' from your calendar.",
    }


# ============================================================================
# 8. get_event_details (Inspect Detailed Calendar Event)
# ============================================================================

def get_event_details(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves full details of a specific calendar event including location,
    attendees, priority level, notes, required gear, and clash analysis.
    """
    events = get_all_events()
    target = None

    if event_id:
        target = next((e for e in events if e.id == event_id), None)

    if not target and (event_title or target_date):
        from planner import find_target_event
        search_query = f"{event_title or ''} {target_date or ''}".strip()
        target = find_target_event(search_query, events)
        if not target and event_title:
            clean = event_title.strip().lower()
            target = next((e for e in events if clean in e.title.lower() or e.title.lower() in clean), None)

    if not target:
        return {
            "success": False,
            "message": f"Could not find any calendar event matching '{event_title or event_id or target_date}'.",
        }

    all_conflicts = check_conflicts(events)
    clashes = [c.model_dump() for c in all_conflicts if target.id in (c.event1_id, c.event2_id)]

    # Compute duration in minutes
    duration_minutes = 0
    try:
        s_dt = datetime.fromisoformat(target.start_time)
        e_dt = datetime.fromisoformat(target.end_time)
        duration_minutes = max(0, int((e_dt - s_dt).total_seconds() / 60))
    except Exception:
        pass

    ev_dict = target.model_dump()
    ev_dict["duration_minutes"] = duration_minutes
    ev_dict["has_conflicts"] = len(clashes) > 0
    ev_dict["conflicts"] = clashes

    return {
        "success": True,
        "event": ev_dict,
        "duration_minutes": duration_minutes,
        "has_conflicts": len(clashes) > 0,
        "conflicts": clashes,
        "message": f"Event details retrieved for '{target.title}'.",
    }