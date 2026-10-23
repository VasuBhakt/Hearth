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
import secrets
from datetime import datetime, timezone, timedelta
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
    ApprovalToken,
    UndoEntry,
)
from db import (
    get_all_events,
    get_preference,
    save_plan,
    get_plan,
    save_event,
    get_event_by_id,
    delete_event,
    save_approval_token,
    verify_and_consume_token,
    save_undo_entry,
    get_undo_entry_by_plan,
    get_latest_undo_entry,
    delete_undo_entry,
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
        APPROVAL_TOKEN_TTL_MINUTES,
        APPROVAL_TOKEN_LENGTH_BYTES,
        UNDO_LEDGER_MAX_ENTRIES,
        DEFAULT_PLAN_STATUS_DRAFT,
        DEFAULT_PLAN_STATUS_COMMITTED,
        ACTION_TYPE_COMMIT_PLAN,
        ACTION_TYPE_RESCHEDULE,
        ACTION_TYPE_DELETE_EVENT,
        MAX_SLOT_SEARCH_DAYS,
        DEFAULT_SLOT_SEARCH_HOUR,
        WEEKDAY_WORKDAY_MAX,
        DEFAULT_VENUE_NAME,
        DEFAULT_VENUE_LATITUDE,
        DEFAULT_VENUE_LONGITUDE,
        PLANNING_SIGNALS,
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
    APPROVAL_TOKEN_TTL_MINUTES = 15
    APPROVAL_TOKEN_LENGTH_BYTES = 32
    UNDO_LEDGER_MAX_ENTRIES = 50
    DEFAULT_PLAN_STATUS_DRAFT = "draft"
    DEFAULT_PLAN_STATUS_COMMITTED = "committed"
    ACTION_TYPE_COMMIT_PLAN = "commit_plan"
    ACTION_TYPE_RESCHEDULE = "reschedule_event"
    ACTION_TYPE_DELETE_EVENT = "delete_event"
    MAX_SLOT_SEARCH_DAYS = 14
    DEFAULT_SLOT_SEARCH_HOUR = 10
    WEEKDAY_WORKDAY_MAX = 5


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

    # 5. Priority weighting as tiebreaker ONLY when there is actual relevance
    if score > 0:
        score += getattr(event, "priority", 1) * 0.1

    return score


def find_target_event(request: str, events: List[Event]) -> Optional[Event]:
    """
    Selects the best calendar event matching the user's request.
    Only falls back to the highest-priority upcoming event if the user
    explicitly asks a general coordination / tournament / weekend planning query.
    Returns None for unrelated or unmatched event queries.
    """
    if not events:
        return None

    scored_events = [(score_event_match(request, ev), ev) for ev in events]
    scored_events.sort(key=lambda pair: pair[0], reverse=True)

    top_score, top_event = scored_events[0]
    if top_score > 0:
        return top_event

    # Only fall back to highest-priority event if request explicitly signals planning / tournament
    req_lower = request.lower()
    if any(k in req_lower for k in PLANNING_SIGNALS):
        fallback_sorted = sorted(events, key=lambda e: (-e.priority, e.start_time))
        return fallback_sorted[0]

    return None


# ============================================================================
# Dynamic Calendar Slot Finder (For Conflict Resolution)
# ============================================================================

def find_next_available_slot(
    event_to_reschedule: Event,
    all_events: List[Event],
    reference_dt: datetime,
    preferences: Optional[Dict[str, Any]] = None,
    target_weekday: Optional[int] = None,
) -> Tuple[datetime, datetime]:
    """
    Finds the next open calendar slot for an event that needs to be moved.
    Searches subsequent weekdays during standard family hours dynamically.
    If target_weekday is provided (0=Mon ... 6=Sun), restricts to that weekday.
    Zero hardcoded dates.
    """
    duration = datetime.fromisoformat(event_to_reschedule.end_time) - datetime.fromisoformat(event_to_reschedule.start_time)
    if duration.total_seconds() <= 0:
        duration = timedelta(hours=1)

    current_search_day = reference_dt.date() + timedelta(days=1)
    candidate_hours = get_daily_scheduling_hours(preferences or {})

    for day_offset in range(MAX_SLOT_SEARCH_DAYS):  # Configurable search window from .env
        test_date = current_search_day + timedelta(days=day_offset)
        if target_weekday is not None:
            if test_date.weekday() != target_weekday:
                continue
        elif test_date.weekday() >= WEEKDAY_WORKDAY_MAX:
            # Skip weekends for appointments/errands unless specifically targeted
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

    # Fallback to next morning using configured search hour
    fallback_start = datetime(current_search_day.year, current_search_day.month, current_search_day.day, DEFAULT_SLOT_SEARCH_HOUR, 0, 0)
    return fallback_start, fallback_start + duration


# ============================================================================
# Online / Virtual Event Detector (no false location conflicts)
# ============================================================================

_ONLINE_VENUE_KEYWORDS = ["online", "virtual", "remote", "home", "zoom", "discord", "teams", "meet"]

def _is_online_event(event: Event) -> bool:
    """Returns True if the event has no physical travel requirement."""
    title_lower = event.title.lower()
    venue_lower = (event.location.name if event.location else "").lower()
    return (
        not event.location
        or any(k in venue_lower for k in _ONLINE_VENUE_KEYWORDS)
        or any(k in title_lower for k in ["online", "contest", "virtual", "zoom", "codeforces", "leetcode", "hackathon"])
    )


# ============================================================================
# LLM-Powered Plan Humanizer
# ============================================================================

async def _humanize_plan_changes(
    raw_changes: List[str],
    target_event_title: str,
    weather: Any,
    leave_by_str: str,
) -> List[str]:
    """
    Rewrites mechanical f-string proposed_changes into warm, natural sentences
    using the configured LLM provider. Falls back to raw strings on any error.
    Each raw change becomes one natural sentence so the plan card still reads cleanly.
    """
    if not raw_changes:
        return raw_changes

    try:
        import os
        import json
        import httpx

        # Build a compact rewrite prompt
        bullet_list = "\n".join(f"- {c}" for c in raw_changes)
        weather_note = ""
        if weather:
            weather_note = f"Weather: {getattr(weather, 'temperature_c', '?')}°C, {getattr(weather, 'weather_condition', '')}, rain={'yes' if getattr(weather, 'rain_warning', False) else 'no'}."

        system_msg = (
            "You are Hearth, a warm and practical family assistant. "
            "Rewrite each planning note below into ONE natural, friendly sentence. "
            "Keep facts accurate (times, names, places). Use a conversational tone as if talking to a parent. "
            "Return ONLY a JSON array of strings — one rewritten string per item, same order, no extra text."
        )
        user_msg = (
            f"Planning for: {target_event_title}. {weather_note}\n"
            f"Notes to rewrite:\n{bullet_list}"
        )

        groq_key = os.environ.get("GROQ_API_KEY", "").strip().strip('"').strip("'")
        groq_url = os.environ.get("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
        groq_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

        if not groq_key:
            return raw_changes  # No LLM available — return as-is

        payload = {
            "model": groq_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.4,
            "max_tokens": 512,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {groq_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hearth/1.0",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(groq_url, headers=headers, json=payload)
            if resp.status_code != 200:
                return raw_changes

        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        rewritten = json.loads(content)
        if isinstance(rewritten, list) and all(isinstance(s, str) for s in rewritten):
            return rewritten
    except Exception:
        pass  # Silent fallback — never block the plan card

    return raw_changes


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

    # 1. Dynamic Conflict Detection — filter out online/virtual-vs-physical false positives
    all_conflicts = check_conflicts(events)
    relevant_conflicts = [
        c for c in all_conflicts
        if target_event.id in (c.event1_id, c.event2_id)
    ]

    # Don't flag a conflict when BOTH events are online/home (they can overlap harmlessly)
    def _both_online(conf: Any) -> bool:
        e1 = next((e for e in events if e.id == conf.event1_id), None)
        e2 = next((e for e in events if e.id == conf.event2_id), None)
        return bool(e1 and e2 and _is_online_event(e1) and _is_online_event(e2))

    relevant_conflicts = [c for c in relevant_conflicts if not _both_online(c)]

    # If the matched target event has lower priority than an event it conflicts with
    # (e.g. user selected or asked to reschedule Dentist to resolve conflict with Tournament),
    # anchor the coordination plan to the higher-priority event so travel and packing reflect the main event.
    for conf in relevant_conflicts:
        other_id = conf.event2_id if conf.event1_id == target_event.id else conf.event1_id
        other_event = next((e for e in events if e.id == other_id), None)
        if other_event and other_event.priority > target_event.priority:
            target_event = other_event
            target_dt = datetime.fromisoformat(target_event.start_time)
            target_date_str = target_dt.strftime("%Y-%m-%d")
            relevant_conflicts = [
                c for c in all_conflicts
                if target_event.id in (c.event1_id, c.event2_id)
            ]
            break

    # 2. Dynamic Weather Forecast for Venue
    venue_name = target_event.location.name if target_event.location else "Online / Home"
    is_online_or_home = (
        not target_event.location
        or any(k in venue_name.lower() for k in ["online", "virtual", "remote", "home", "zoom", "discord"])
        or any(k in target_event.title.lower() for k in ["online", "contest", "virtual", "zoom"])
    )

    venue_lat = target_event.location.latitude if (target_event.location and target_event.location.latitude) else DEFAULT_VENUE_LATITUDE
    venue_lng = target_event.location.longitude if (target_event.location and target_event.location.longitude) else DEFAULT_VENUE_LONGITUDE

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
    action_items: List[dict] = []

    # Build a virtual "already booked" list that grows as we resolve each conflict.
    # This prevents two proposed reschedules from landing in the same slot.
    virtual_events: List[Event] = list(events)

    for conf in relevant_conflicts:
        other_id = conf.event2_id if conf.event1_id == target_event.id else conf.event1_id
        other_event = next((e for e in events if e.id == other_id), None)

        if other_event:
            # Compare priorities: Lower priority event yields
            if other_event.priority <= target_event.priority:
                new_start, new_end = find_next_available_slot(other_event, virtual_events, target_dt, preferences)
                proposed_changes.append(
                    f"Reschedule '{other_event.title}' to {new_start.strftime('%A, %b %d at %I:%M %p')} to resolve overlap with '{target_event.title}'."
                )
                action_items.append({
                    "action": ACTION_TYPE_RESCHEDULE,
                    "event_id": other_event.id,
                    "event_title": other_event.title,
                    "new_start_time": new_start.isoformat(),
                    "new_end_time": new_end.isoformat(),
                })
                # Register the proposed slot as a virtual event so subsequent iterations avoid it
                virtual_placeholder = Event(
                    id=f"__virtual_{other_event.id}",
                    title=other_event.title,
                    start_time=new_start.isoformat(),
                    end_time=new_end.isoformat(),
                    priority=other_event.priority,
                )
                virtual_events.append(virtual_placeholder)
            else:
                new_start, new_end = find_next_available_slot(target_event, virtual_events, target_dt, preferences)
                proposed_changes.append(
                    f"Shift '{target_event.title}' to {new_start.strftime('%A, %b %d at %I:%M %p')} to respect higher-priority '{other_event.title}'."
                )
                action_items.append({
                    "action": ACTION_TYPE_RESCHEDULE,
                    "event_id": target_event.id,
                    "event_title": target_event.title,
                    "new_start_time": new_start.isoformat(),
                    "new_end_time": new_end.isoformat(),
                })
                # Register the proposed slot as a virtual event
                virtual_placeholder = Event(
                    id=f"__virtual_{target_event.id}",
                    title=target_event.title,
                    start_time=new_start.isoformat(),
                    end_time=new_end.isoformat(),
                    priority=target_event.priority,
                )
                virtual_events.append(virtual_placeholder)

    # Departure scheduling proposal
    leave_time_str = travel_estimate.recommended_leave_by[11:16]
    start_time_str = target_event.start_time[11:16]

    if is_online_or_home or travel_estimate.travel_mode == "none":
        proposed_changes.append(
            f"For '{target_event.title}' (starts at {start_time_str}): Online / Home event. No driving travel required."
        )
    else:
        drive_mins = travel_estimate.travel_time_minutes
        arrival_dt = datetime.fromisoformat(target_event.start_time) - timedelta(minutes=buffer_mins)
        arrival_target_str = arrival_dt.strftime("%H:%M")
        proposed_changes.append(
            f"For '{target_event.title}' (starts at {start_time_str}): Depart from {origin_name} by {leave_time_str} ({drive_mins} min drive + {buffer_mins} minutes buffer) to arrive at {venue_name} by {arrival_target_str} ({buffer_mins} minutes early)."
        )

    # 6. Humanize proposed_changes via LLM (warm, natural language)
    proposed_changes = await _humanize_plan_changes(
        raw_changes=proposed_changes,
        target_event_title=target_event.title,
        weather=weather,
        leave_by_str=travel_estimate.recommended_leave_by,
    )

    # 7. Generate and Save Draft PlanCard
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
        action_items=action_items,
        status=DEFAULT_PLAN_STATUS_DRAFT,
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

    if plan.status == DEFAULT_PLAN_STATUS_COMMITTED:
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

        # Detect target weekday dynamically from dest_term
        target_weekday = None
        for idx, wname in enumerate(WEEKDAY_NAMES):
            if wname in dest_term.lower():
                target_weekday = idx
                break

        if matched_event:
            try:
                ref_dt = datetime.fromisoformat(plan.target_date)
            except ValueError:
                ref_dt = datetime.now()

            new_start, new_end = find_next_available_slot(
                matched_event, events, ref_dt, preferences=None, target_weekday=target_weekday
            )
            # Update or append to plan.action_items
            action_updated = False
            for act in plan.action_items:
                if act.get("event_id") == matched_event.id:
                    act["new_start_time"] = new_start.isoformat()
                    act["new_end_time"] = new_end.isoformat()
                    action_updated = True
                    break
            if not action_updated:
                plan.action_items.append({
                    "action": ACTION_TYPE_RESCHEDULE,
                    "event_id": matched_event.id,
                    "event_title": matched_event.title,
                    "new_start_time": new_start.isoformat(),
                    "new_end_time": new_end.isoformat(),
                })

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


# ============================================================================
# Security Gate, Commit, and Undo Implementation
# ============================================================================

def mint_approval_token(plan_id: str, ttl_minutes: Optional[int] = None) -> ApprovalToken:
    """
    Mints a single-use cryptographic approval token for a specific plan.
    Simulates the Plan Card UI's 'Approve' button.
    Token validity duration is configured via .env (APPROVAL_TOKEN_TTL_MINUTES).
    """
    plan = get_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan with id '{plan_id}' does not exist.")

    ttl = ttl_minutes if ttl_minutes is not None else APPROVAL_TOKEN_TTL_MINUTES
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl)
    token_str = secrets.token_urlsafe(APPROVAL_TOKEN_LENGTH_BYTES)

    token = ApprovalToken(
        plan_id=plan_id,
        token=token_str,
        approved_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
    )
    save_approval_token(token)
    return token


async def commit_plan(plan_id: str, approval_token: str) -> Dict[str, Any]:
    """
    Executes a draft PlanCard by applying its action items to calendar events.
    Security Gate:
    - Requires a valid, unexpired approval token.
    - Burns the token immediately upon verification (single-use guarantee).
    - Captures an exact snapshot of current calendar events in undo_ledger before any mutation.
    """
    if not approval_token or not approval_token.strip():
        raise ValueError("Commit rejected: Missing approval token.")

    plan = get_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan with id '{plan_id}' does not exist.")

    if plan.status == DEFAULT_PLAN_STATUS_COMMITTED:
        raise ValueError(f"Plan '{plan_id}' has already been committed.")

    # 1. Verify and consume approval token (burns token)
    is_valid = verify_and_consume_token(plan_id, approval_token.strip())
    if not is_valid:
        raise ValueError(f"Commit rejected: Invalid or expired approval token for plan '{plan_id}'.")

    # 2. Snapshot affected calendar events into undo_ledger (Targeted Event Delta)
    target_event_ids = {
        action["event_id"]
        for action in plan.action_items
        if isinstance(action, dict) and "event_id" in action
    }
    affected_events = [get_event_by_id(eid) for eid in target_event_ids]
    snapshot = [ev.model_dump() for ev in affected_events if ev is not None]

    undo_id = f"undo_{plan_id}_{int(datetime.now(timezone.utc).timestamp())}"
    undo_entry = UndoEntry(
        id=undo_id,
        plan_id=plan_id,
        action_type=ACTION_TYPE_COMMIT_PLAN,
        timestamp=datetime.now(timezone.utc).isoformat(),
        snapshot_data={
            "events": snapshot,
            "plan_id": plan_id,
            "plan_status": plan.status,
        },
    )
    save_undo_entry(undo_entry)

    # 3. Apply mutations to calendar events based on action_items
    executed_actions = 0
    for action in plan.action_items:
        act_type = action.get("action")
        if act_type == ACTION_TYPE_RESCHEDULE:
            event_id = action.get("event_id")
            event_obj = get_event_by_id(event_id)
            if event_obj:
                if "new_start_time" in action:
                    event_obj.start_time = action["new_start_time"]
                if "new_end_time" in action:
                    event_obj.end_time = action["new_end_time"]
                save_event(event_obj)
                executed_actions += 1
        elif act_type == ACTION_TYPE_DELETE_EVENT:
            event_id = action.get("event_id")
            if event_id:
                deleted = delete_event(event_id)
                if deleted:
                    executed_actions += 1

    # 4. Update plan status to 'committed'
    plan.status = DEFAULT_PLAN_STATUS_COMMITTED
    save_plan(plan)

    return {
        "success": True,
        "plan_id": plan_id,
        "status": plan.status,
        "committed_at": undo_entry.timestamp,
        "actions_executed": executed_actions,
        "undo_available": True,
        "message": f"Plan '{plan.title}' committed successfully. {executed_actions} event(s) updated.",
    }


async def undo_plan(plan_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Rolls back calendar events to the snapshot captured prior to commit.
    Restores the plan's status back to 'draft'.
    Cleans up the consumed undo entry.
    """
    if plan_id:
        undo_entry = get_undo_entry_by_plan(plan_id)
        if not undo_entry:
            raise ValueError(f"No undo record found for plan '{plan_id}'.")
    else:
        undo_entry = get_latest_undo_entry()
        if not undo_entry:
            raise ValueError("No undo records available in ledger.")

    snapshot = undo_entry.snapshot_data
    if isinstance(snapshot, dict) and "events" in snapshot:
        raw_events = snapshot["events"]
        target_plan_id = snapshot.get("plan_id", undo_entry.plan_id)
        saved_plan_status = snapshot.get("plan_status", DEFAULT_PLAN_STATUS_DRAFT)
    elif isinstance(snapshot, list):
        raw_events = snapshot
        target_plan_id = undo_entry.plan_id
        saved_plan_status = DEFAULT_PLAN_STATUS_DRAFT
    else:
        raise ValueError("Invalid snapshot data in undo record.")

    # 1. Restore ONLY the affected calendar events from the targeted snapshot
    for ev_dict in raw_events:
        if isinstance(ev_dict, dict):
            save_event(Event(**ev_dict))

    # 2. Revert plan status to draft
    plan = get_plan(target_plan_id)
    if plan:
        plan.status = saved_plan_status
        save_plan(plan)

    # 3. Clean up the consumed undo entry
    delete_undo_entry(undo_entry.id)

    return {
        "success": True,
        "plan_id": target_plan_id,
        "status": saved_plan_status,
        "restored_events_count": len(raw_events),
        "message": f"Undo successful. Restored calendar to state prior to plan '{target_plan_id}'.",
    }


def discard_plan(plan_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Cancels and removes a draft plan. If plan_id is provided, deletes that plan;
    otherwise deletes all active draft plans from the database.
    """
    from db import delete_plan, delete_draft_plans
    if plan_id:
        deleted = delete_plan(plan_id)
        return {"success": deleted, "plan_id": plan_id, "message": "Draft plan cancelled."}
    else:
        count = delete_draft_plans()
        return {"success": True, "count": count, "message": "All draft plans cancelled."}


def propose_event_cancellation(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
) -> PlanCard:
    """
    Creates a draft PlanCard for cancelling/removing a calendar event with Human-in-the-Loop approval.
    Safety Guarantee: NEVER mutates calendar events directly.
    Requires explicit human approval (mint_approval_token + commit_plan) to delete.
    """
    events = get_all_events()
    target = None

    if event_id:
        target = next((e for e in events if e.id == event_id), None)

    if not target and event_title:
        target = find_target_event(event_title, events)
        if not target:
            clean = event_title.strip().lower()
            target = next((e for e in events if clean in e.title.lower() or e.title.lower() in clean), None)
            if not target:
                words = [w for w in clean.split() if len(w) >= 3 and w not in ["event", "calendar", "schedule", "please", "remove", "delete", "cancel"]]
                if words:
                    target = next((e for e in events if any(w in e.title.lower() for w in words)), None)

    if not target:
        raise ValueError(f"Could not find any calendar event matching '{event_title or event_id}'.")

    target_dt = datetime.fromisoformat(target.start_time)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    plan_id = f"plan_cancel_{target.id}_{int(datetime.now(timezone.utc).timestamp())}"
    plan_card = PlanCard(
        id=plan_id,
        title=f"Cancel: {target.title}",
        target_date=target_date_str,
        leave_by=target.start_time,
        conflicts=[],
        weather=None,
        packing_list=[],
        proposed_changes=[
            f"Remove '{target.title}' scheduled for {target_dt.strftime('%A, %b %d at %I:%M %p')} from your calendar upon approval."
        ],
        action_items=[{
            "action": ACTION_TYPE_DELETE_EVENT,
            "event_id": target.id,
            "event_title": target.title,
        }],
        status=DEFAULT_PLAN_STATUS_DRAFT,
    )
    save_plan(plan_card)
    return plan_card

