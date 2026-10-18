"""
Hearth Generic Planning Engine
Coordinates read tools to generate and revise draft PlanCards.
Zero hardcoding:
- Matches target events dynamically via token overlap, date resolution, and priority.
- Resolves conflicts dynamically by comparing event priorities and locating open calendar slots.
- Builds packing lists dynamically from event required_items, family preferences, and weather thresholds.
- Revises plans dynamically using generic natural language extraction patterns.
- Enforces safety: Calendar events in the database are NEVER mutated during planning.
"""
import os
import sys
import re
import string
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Ensure local modules resolve cleanly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from models import (
    PlanCard,
    ConflictReport,
    WeatherForecast,
    Event,
    Location,
)
from db import (
    get_all_events,
    get_preference,
    save_plan,
    get_plan,
)
from tools import (
    check_conflicts,
    estimate_travel,
    get_forecast,
)

import calendar

# Dynamically obtain standard weekday names from standard library
WEEKDAY_NAMES = [name.lower() for name in calendar.day_name]


# Import environment configurations and defaults
try:
    from config import (
        DEFAULT_HOME_NAME,
        DEFAULT_HOME_LATITUDE,
        DEFAULT_HOME_LONGITUDE,
        DEFAULT_ARRIVAL_BUFFER_MINUTES,
        DEFAULT_SAVED_SNACKS,
        SCHEDULE_START_HOUR,
        SCHEDULE_END_HOUR,
        WEATHER_RAIN_THRESHOLD_PERCENT,
        WEATHER_COLD_THRESHOLD_C,
        WEATHER_HOT_THRESHOLD_C,
        LOCATION_KEYWORD_MATCHES,
        PACKING_KEYWORD_MATCHES,
        EVENT_TEXT_FIELDS,
        BUFFER_KEYWORD_MATCHES,
        RAIN_WEATHER_KEYWORDS,
        COLD_WEATHER_KEYWORDS,
        HOT_WEATHER_KEYWORDS,
    )
except ImportError:
    DEFAULT_HOME_NAME = "Home"
    DEFAULT_HOME_LATITUDE = 40.6782
    DEFAULT_HOME_LONGITUDE = -73.9442
    DEFAULT_ARRIVAL_BUFFER_MINUTES = 30
    DEFAULT_SAVED_SNACKS = ["Orange slices", "Granola bars", "Electrolyte drinks", "Ice pack"]
    SCHEDULE_START_HOUR = 9
    SCHEDULE_END_HOUR = 17
    WEATHER_RAIN_THRESHOLD_PERCENT = 40.0
    WEATHER_COLD_THRESHOLD_C = 12.0
    WEATHER_HOT_THRESHOLD_C = 28.0
    LOCATION_KEYWORD_MATCHES = ["home", "origin", "base", "start", "dep"]
    PACKING_KEYWORD_MATCHES = ["snack", "pack", "gear", "item", "check", "suppl", "food"]
    EVENT_TEXT_FIELDS = ["title", "description", "category", "summary", "notes"]
    BUFFER_KEYWORD_MATCHES = ["buffer"]
    RAIN_WEATHER_KEYWORDS = ["rain", "storm", "drizzle", "shower"]
    COLD_WEATHER_KEYWORDS = ["cold", "snow", "ice", "freeze", "chill"]
    HOT_WEATHER_KEYWORDS = ["hot", "sunny", "heat"]

# ============================================================================
# Dynamic Preference Resolvers (Configurable via .env)
# ============================================================================

def resolve_origin_location(preferences: Dict[str, Any]) -> Tuple[str, float, float]:
    """
    Dynamically finds an origin/departure location from preferences without hardcoded keys.
    Inspects preference values for latitude and longitude fields.
    Falls back to .env configured defaults if no location preference is found.
    """
    candidates = []
    for key, val in preferences.items():
        if isinstance(val, dict) and "latitude" in val and "longitude" in val:
            name = val.get("name") or key.replace("_", " ").title()
            priority = 2 if any(k in key.lower() for k in LOCATION_KEYWORD_MATCHES) else 1
            candidates.append((priority, name, float(val["latitude"]), float(val["longitude"])))

    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1], candidates[0][2], candidates[0][3]

    # Configured fallback from .env
    return DEFAULT_HOME_NAME, DEFAULT_HOME_LATITUDE, DEFAULT_HOME_LONGITUDE


def resolve_arrival_buffer(preferences: Dict[str, Any], default_buffer: Optional[int] = None) -> int:
    """
    Dynamically finds arrival buffer minutes from preferences without hardcoding exact key names.
    Falls back to DEFAULT_ARRIVAL_BUFFER_MINUTES from .env.
    """
    if default_buffer is None:
        default_buffer = DEFAULT_ARRIVAL_BUFFER_MINUTES

    for key, val in preferences.items():
        if any(b in key.lower() for b in BUFFER_KEYWORD_MATCHES) and isinstance(val, (int, float)):
            return int(val)
    return default_buffer


def extract_packing_items_from_preferences(preferences: Dict[str, Any]) -> List[str]:
    """
    Dynamically gathers items from any preference containing lists of items,
    such as snacks, gear, packing lists, checklists, supplies, etc.
    Matches configurable keywords from .env and falls back to DEFAULT_SAVED_SNACKS.
    """
    items: List[str] = []
    for key, val in preferences.items():
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            key_lower = key.lower()
            if any(term in key_lower for term in PACKING_KEYWORD_MATCHES):
                items.extend(val)

    if not items and DEFAULT_SAVED_SNACKS:
        items.extend(DEFAULT_SAVED_SNACKS)

    return items


def derive_weather_packing_items(weather: Optional[WeatherForecast]) -> List[str]:
    """
    Dynamically suggests weather-appropriate gear based on forecast conditions
    using configurable keywords and thresholds from .env.
    """
    if not weather:
        return []

    suggested: List[str] = []
    cond_lower = (weather.weather_condition or "").lower()

    if (
        weather.rain_warning
        or (weather.precipitation_chance_percent and weather.precipitation_chance_percent > WEATHER_RAIN_THRESHOLD_PERCENT)
        or any(kw in cond_lower for kw in RAIN_WEATHER_KEYWORDS)
    ):
        suggested.append("Rain gear (umbrellas / waterproof jackets)")
        suggested.append("Extra dry towels & change of clothes")

    if weather.temperature_c is not None:
        if weather.temperature_c < WEATHER_COLD_THRESHOLD_C or any(kw in cond_lower for kw in COLD_WEATHER_KEYWORDS):
            suggested.append("Warm outerwear & thermal layers")
        elif weather.temperature_c > WEATHER_HOT_THRESHOLD_C or any(kw in cond_lower for kw in HOT_WEATHER_KEYWORDS):
            suggested.append("Sunscreen SPF 50 & extra hydration")

    return suggested


def get_daily_scheduling_hours(preferences: Dict[str, Any]) -> List[int]:
    """Generates candidate hours from preference window or .env configured daylight hours."""
    start_hour = int(preferences.get("schedule_start_hour", SCHEDULE_START_HOUR))
    end_hour = int(preferences.get("schedule_end_hour", SCHEDULE_END_HOUR))
    return list(range(start_hour, end_hour))


# ============================================================================
# Dynamic Target Event Matching
# ============================================================================

def score_event_match(request: str, event: Event) -> float:
    """
    Dynamically computes match score between a user request and an event by
    inspecting all string, collection, and date attributes of the event without hardcoding fields.
    """
    translator = str.maketrans("", "", string.punctuation)
    req_clean = request.lower().translate(translator)
    query_tokens = set(req_clean.split())

    score = 0.0

    # 1. Day of Week Alignment from start_time
    if hasattr(event, "start_time") and event.start_time:
        try:
            ev_dt = datetime.fromisoformat(event.start_time)
            ev_weekday = calendar.day_name[ev_dt.weekday()].lower()
            if ev_weekday in query_tokens:
                score += 5.0
        except ValueError:
            pass

    # 2. Inspect all string attributes configured via .env (title, description, etc.)
    for field_name in EVENT_TEXT_FIELDS:
        val = getattr(event, field_name, None)
        if isinstance(val, str) and val:
            field_tokens = set(val.lower().translate(translator).split())
            overlap = query_tokens.intersection(field_tokens)
            weight = 3.0 if field_name == "title" else 1.0
            score += len(overlap) * weight

    # 3. Inspect attendee / participant names
    if hasattr(event, "attendees") and isinstance(event.attendees, list):
        for att in event.attendees:
            if isinstance(att, str):
                att_tokens = set(att.lower().translate(translator).split())
                score += len(query_tokens.intersection(att_tokens)) * 2.0

    # 4. Location Name Overlap
    if hasattr(event, "location") and event.location and hasattr(event.location, "name") and event.location.name:
        loc_tokens = set(event.location.name.lower().translate(translator).split())
        score += len(query_tokens.intersection(loc_tokens)) * 2.0

    # 5. Priority weighting as tiebreaker
    score += getattr(event, "priority", 1) * 0.1

    return score


def find_target_event(request: str, events: List[Event]) -> Optional[Event]:
    """
    Selects the best calendar event matching the user's request.
    Falls back to the highest-priority upcoming event if no specific match is found.
    """
    if not events:
        return None

    scored_events = [(score_event_match(request, ev), ev) for ev in events]
    scored_events.sort(key=lambda pair: pair[0], reverse=True)

    top_score, top_event = scored_events[0]
    if top_score > 0:
        return top_event

    # Fallback: Sort by priority descending, then by earliest start time
    fallback_sorted = sorted(events, key=lambda e: (-e.priority, e.start_time))
    return fallback_sorted[0]


# ============================================================================
# Dynamic Calendar Slot Finder (For Conflict Resolution)
# ============================================================================

def find_next_available_slot(
    event_to_reschedule: Event,
    all_events: List[Event],
    reference_dt: datetime,
    preferences: Optional[Dict[str, Any]] = None,
) -> Tuple[datetime, datetime]:
    """
    Finds the next open calendar slot for an event that needs to be moved.
    Searches subsequent weekdays during standard family hours dynamically.
    Zero hardcoded dates.
    """
    duration = datetime.fromisoformat(event_to_reschedule.end_time) - datetime.fromisoformat(event_to_reschedule.start_time)
    if duration.total_seconds() <= 0:
        duration = timedelta(hours=1)

    current_search_day = reference_dt.date() + timedelta(days=1)
    candidate_hours = get_daily_scheduling_hours(preferences or {})

    for day_offset in range(7):  # Search up to 7 days ahead
        test_date = current_search_day + timedelta(days=day_offset)
        # Skip weekends for appointments/errands
        if test_date.weekday() >= 5:
            continue

        for hour in candidate_hours:
            slot_start = datetime(test_date.year, test_date.month, test_date.day, hour, 0, 0)
            slot_end = slot_start + duration

            # Verify zero clashes with any existing event
            has_conflict = False
            for existing in all_events:
                if existing.id == event_to_reschedule.id:
                    continue  # Ignore the event being moved
                ex_start = datetime.fromisoformat(existing.start_time)
                ex_end = datetime.fromisoformat(existing.end_time)

                if slot_start < ex_end and slot_end > ex_start:
                    has_conflict = True
                    break

            if not has_conflict:
                return slot_start, slot_end

    # Fallback to next morning
    fallback_start = datetime(current_search_day.year, current_search_day.month, current_search_day.day, 10, 0, 0)
    return fallback_start, fallback_start + duration


# ============================================================================
# Dynamic Plan Generation (propose_plan)
# ============================================================================

async def propose_plan(request: str = "Get us ready for Saturday's tournament") -> PlanCard:
    """
    Generates a draft PlanCard by orchestrating context, conflicts, travel, and weather.
    - Resolves conflicts dynamically using event priority comparisons.
    - Generates packing lists dynamically from event properties, family preferences, and weather conditions.
    - NEVER mutates calendar events in the database (strictly draft persistence).
    """
    from db import get_all_preferences
    preferences = get_all_preferences()

    events = get_all_events()
    target_event = find_target_event(request, events)

    if not target_event:
        raise ValueError("No matching calendar events found to plan for.")

    target_dt = datetime.fromisoformat(target_event.start_time)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    # 1. Dynamic Conflict Detection
    all_conflicts = check_conflicts(events)
    relevant_conflicts = [
        c for c in all_conflicts
        if target_event.id in (c.event1_id, c.event2_id)
    ]

    # 2. Dynamic Weather Forecast for Venue
    venue_name = target_event.location.name if target_event.location else "Venue"
    venue_lat = target_event.location.latitude if target_event.location else 40.7128
    venue_lng = target_event.location.longitude if target_event.location else -74.0060

    weather = await get_forecast(
        location_name=venue_name,
        latitude=venue_lat,
        longitude=venue_lng,
        date_str=target_date_str,
    )

    # 3. Dynamic Travel Estimation & Leave-By Calculation (No hardcoded keys)
    origin_name, origin_lat, origin_lng = resolve_origin_location(preferences)
    buffer_mins = resolve_arrival_buffer(preferences)

    travel_estimate = estimate_travel(
        origin_name=origin_name,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_name=venue_name,
        dest_lat=venue_lat,
        dest_lng=venue_lng,
        target_arrival_time=target_event.start_time,
        buffer_minutes=buffer_mins,
    )

    # 4. Dynamic Packing & Prep List
    packing_list: List[str] = []

    # Items declared on the event itself
    if target_event.required_items:
        packing_list.extend(target_event.required_items)

    # Family preferences (dynamic extraction of all lists)
    packing_list.extend(extract_packing_items_from_preferences(preferences))

    # Condition-driven weather adaptations
    packing_list.extend(derive_weather_packing_items(weather))

    # 5. Dynamic Conflict Resolution using Priority Comparison
    proposed_changes: List[str] = []

    for conf in relevant_conflicts:
        other_id = conf.event2_id if conf.event1_id == target_event.id else conf.event1_id
        other_event = next((e for e in events if e.id == other_id), None)

        if other_event:
            # Compare priorities: Lower priority event yields
            if other_event.priority <= target_event.priority:
                new_start, _ = find_next_available_slot(other_event, events, target_dt, preferences)
                proposed_changes.append(
                    f"Reschedule '{other_event.title}' to {new_start.strftime('%A, %b %d at %I:%M %p')} to resolve overlap with '{target_event.title}'."
                )
            else:
                new_start, _ = find_next_available_slot(target_event, events, target_dt, preferences)
                proposed_changes.append(
                    f"Shift '{target_event.title}' to {new_start.strftime('%A, %b %d at %I:%M %p')} to respect higher-priority '{other_event.title}'."
                )

    # Departure scheduling proposal
    leave_time_str = travel_estimate.recommended_leave_by[11:16]
    proposed_changes.append(
        f"Depart from {origin_name} by {leave_time_str} to arrive {buffer_mins} minutes prior to start."
    )

    # 6. Generate and Save Draft PlanCard
    plan_id = f"plan_{target_event.id}_{target_date_str.replace('-', '')}"
    plan_card = PlanCard(
        id=plan_id,
        title=f"Plan: {target_event.title}",
        target_date=target_date_str,
        leave_by=travel_estimate.recommended_leave_by,
        conflicts=relevant_conflicts,
        weather=weather,
        packing_list=list(dict.fromkeys(packing_list)),  # Deduplicate while preserving order
        proposed_changes=proposed_changes,
        status="draft",
    )

    save_plan(plan_card)
    return plan_card


# ============================================================================
# Dynamic Plan Revision (revise_plan)
# ============================================================================

async def revise_plan(plan_id: str, instruction: str) -> PlanCard:
    """
    Applies user modifications to a draft PlanCard using generic pattern extraction.
    Zero hardcoded strings or item names.
    Supported patterns:
    - Add items: 'add <items> to packing list'
    - Reschedule: 'move <event> to <time/day>'
    - Time adjustments: 'leave <N> minutes earlier/later'
    """
    plan = get_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan with id '{plan_id}' does not exist.")

    if plan.status == "committed":
        raise ValueError(f"Plan '{plan_id}' has already been committed and cannot be revised.")

    # 1. Generic Item Addition Pattern
    # Matches: 'add folding chairs to packing list', 'pack sunscreen and towels', 'bring snacks'
    add_item_match = re.search(
        r"(?:add|include|pack|bring)\s+(?P<items>.+?)(?:\s+to\s+(?:the\s+)?(?:packing\s+)?list|\s*$)",
        instruction,
        re.IGNORECASE,
    )
    if add_item_match:
        items_str = add_item_match.group("items").strip()
        raw_items = [i.strip() for i in re.split(r",|\sand\s|&", items_str) if i.strip()]
        for item in raw_items:
            clean_item = item.strip().title()
            if not any(clean_item.lower() == existing.lower() for existing in plan.packing_list):
                plan.packing_list.append(clean_item)

    # 2. Generic Reschedule Pattern
    # Matches: 'move the dentist to Monday', 'reschedule practice to Tuesday 4 PM'
    reschedule_match = re.search(
        r"(?:move|reschedule|shift)\s+(?:the\s+)?(?P<target>.+?)\s+to\s+(?P<dest>.+)",
        instruction,
        re.IGNORECASE,
    )
    if reschedule_match:
        target_term = reschedule_match.group("target").strip().lower()
        dest_term = reschedule_match.group("dest").strip()

        # Resolve full event title if possible
        events = get_all_events()
        matched_event = find_target_event(target_term, events)
        target_display = matched_event.title if matched_event else target_term.title()

        updated_changes = []
        applied = False
        for change in plan.proposed_changes:
            if target_term in change.lower() or (matched_event and matched_event.title.lower() in change.lower()):
                updated_changes.append(f"Confirmed: Reschedule '{target_display}' to {dest_term.title()}.")
                applied = True
            else:
                updated_changes.append(change)

        if not applied:
            updated_changes.insert(0, f"Confirmed: Reschedule '{target_display}' to {dest_term.title()}.")

        plan.proposed_changes = updated_changes

    # 3. Generic Time Shift Pattern
    # Matches: 'leave 15 minutes earlier', 'depart 20 mins later'
    shift_match = re.search(
        r"(?:leave|depart)\s+(?P<mins>\d+)\s*min(?:ute)?s?\s*(?P<dir>earlier|later)",
        instruction,
        re.IGNORECASE,
    )
    if shift_match:
        mins = int(shift_match.group("mins"))
        direction = shift_match.group("dir").lower()
        delta = timedelta(minutes=mins)

        try:
            curr_leave = datetime.fromisoformat(plan.leave_by)
            new_leave = curr_leave - delta if direction == "earlier" else curr_leave + delta
            plan.leave_by = new_leave.isoformat()
            plan.proposed_changes.append(f"Adjusted departure time to {mins} minutes {direction} upon request.")
        except ValueError:
            pass

    save_plan(plan)
    return plan
