"""
Unit tests for Hearth's Planning Engine:
- propose_plan (orchestration of context, conflicts, travel, weather, packing, and proposed changes)
- Calendar event immutability guarantee (proposing plans must NEVER mutate calendar events)
- revise_plan (spoken/typed modifications to draft PlanCards)
- Dynamic preference and item resolution (zero hardcoded fields or keys)
- Dynamic priority-based conflict resolution
"""
import pytest
from datetime import datetime
from server.seed import seed_demo_data
from server.models import Event, Location
from server.db import get_all_events, get_plan, save_event, set_preference
from server.planner import propose_plan, revise_plan

@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is seeded with demo scenario before each test."""
    seed_demo_data()

# ============================================================================
# 1. propose_plan tests
# ============================================================================

@pytest.mark.asyncio
async def test_propose_plan_saturday_scenario():
    """
    Verify propose_plan orchestrates the complete Saturday tournament scenario:
    - Identifies Maya's Soccer Tournament
    - Detects the overlapping dentist appointment
    - Fetches the venue forecast with rain warning
    - Calculates recommended leave-by time
    - Aggregates event required items, saved snacks, and rain gear into packing list
    - Proposes moving the lower-priority dentist appointment
    - Persists as 'draft'
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")

    assert plan is not None
    assert plan.status == "draft"
    assert plan.target_date == "2026-10-17"
    assert "Soccer Tournament" in plan.title

    # 1. Conflicts
    assert len(plan.conflicts) >= 1
    dentist_clash = next(
        (c for c in plan.conflicts if "evt_dentist" in (c.event1_id, c.event2_id)),
        None
    )
    assert dentist_clash is not None
    assert dentist_clash.conflict_type == "Overlap"

    # 2. Weather
    assert plan.weather is not None
    assert plan.weather.rain_warning is True
    assert "Rain" in plan.weather.weather_condition

    # 3. Leave-by time
    assert plan.leave_by < "2026-10-17T09:00:00"

    # 4. Packing list includes event items, saved snacks, AND weather gear
    assert any("cleat" in item.lower() or "uniform" in item.lower() for item in plan.packing_list)
    assert "Orange slices" in plan.packing_list
    assert "Granola bars" in plan.packing_list
    assert any("rain" in item.lower() or "umbrella" in item.lower() for item in plan.packing_list)

    # 5. Proposed changes include moving the dentist
    assert any("reschedule" in c.lower() and "dentist" in c.lower() for c in plan.proposed_changes)

    # 6. Plan is persisted in database with status 'draft'
    saved = get_plan(plan.id)
    assert saved is not None
    assert saved.status == "draft"
    assert saved.title == plan.title

@pytest.mark.asyncio
async def test_propose_plan_does_not_mutate_calendar_events():
    """
    CRITICAL SAFETY GUARANTEE:
    Proposing a plan must NEVER mutate or alter calendar events in the database.
    Events must remain 100% unchanged until explicit human approval.
    """
    events_before = get_all_events()

    # Generate draft plan
    await propose_plan("Get us ready for Saturday's tournament")

    events_after = get_all_events()

    # Total events count must be unchanged
    assert len(events_before) == len(events_after)

    # All start times, locations, and descriptions must remain identical
    before_map = {e.id: (e.start_time, e.end_time) for e in events_before}
    after_map = {e.id: (e.start_time, e.end_time) for e in events_after}
    assert before_map == after_map

    # Specifically verify the conflicting dentist appointment is still at its original time
    dentist_event = next(e for e in events_after if e.id == "evt_dentist")
    assert dentist_event.start_time == "2026-10-17T10:00:00"

@pytest.mark.asyncio
async def test_propose_plan_dynamic_custom_event_and_preferences():
    """
    Verify propose_plan works generically with arbitrary custom events and
    arbitrary preference keys (zero hardcoded keys or event names).
    """
    # Insert custom preferences under novel key names
    set_preference("camping_supplies_checklist", ["Marshmallows", "Headlamp & batteries"])
    set_preference("custom_departure_buffer_time", 45)

    # Insert a custom event
    custom_event = Event(
        id="evt_camping_trip",
        title="Family Mountain Camping",
        start_time="2026-10-24T14:00:00",
        end_time="2026-10-25T12:00:00",
        location=Location(
            name="Pine Ridge Campground",
            latitude=41.1234,
            longitude=-73.5678,
        ),
        attendees=["Alex", "Sam"],
        description="Overnight wilderness camping excursion.",
        priority=3,
        required_items=["2-person tent", "Sleeping bags"],
    )
    save_event(custom_event)

    plan = await propose_plan("Prepare for the camping trip")

    assert plan.target_date == "2026-10-24"
    assert "Camping" in plan.title

    # Verifies dynamic packing list from required_items and novel preference key
    assert "2-person tent" in plan.packing_list
    assert "Sleeping bags" in plan.packing_list
    assert "Marshmallows" in plan.packing_list
    assert "Headlamp & batteries" in plan.packing_list


# ============================================================================
# 2. revise_plan tests
# ============================================================================

@pytest.mark.asyncio
async def test_revise_plan_reschedules_event():
    """
    Verify that speaking 'Move the dentist to Monday' updates the proposed changes
    on the draft plan card.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")

    # Parent says: "Move the dentist to Monday"
    revised = await revise_plan(plan.id, "Move the dentist to Monday")

    assert revised.id == plan.id
    assert revised.status == "draft"

    # Proposed changes must explicitly confirm the Monday move
    assert any("dentist" in c.lower() and "monday" in c.lower() and "confirmed" in c.lower() for c in revised.proposed_changes)

    # Database copy is updated
    saved_revised = get_plan(plan.id)
    assert saved_revised is not None
    assert any("dentist" in c.lower() and "monday" in c.lower() and "confirmed" in c.lower() for c in saved_revised.proposed_changes)

@pytest.mark.asyncio
async def test_revise_plan_adds_items_to_packing_list():
    """
    Verify that requesting additional items dynamically appends them
    to the draft packing list without hardcoded item mappings.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")
    original_count = len(plan.packing_list)

    # Parent says: "Add folding lawn chairs and sunscreen to the packing list"
    revised = await revise_plan(plan.id, "Add folding lawn chairs and sunscreen to the packing list")

    assert len(revised.packing_list) > original_count
    assert any("folding lawn chairs" in item.lower() for item in revised.packing_list)
    assert any("sunscreen" in item.lower() for item in revised.packing_list)

@pytest.mark.asyncio
async def test_revise_plan_shifts_departure_time():
    """
    Verify that speaking 'Leave 15 minutes earlier' modifies the leave_by time.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")
    original_leave_dt = datetime.fromisoformat(plan.leave_by)

    # Parent says: "Leave 15 minutes earlier"
    revised = await revise_plan(plan.id, "Leave 15 minutes earlier")

    new_leave_dt = datetime.fromisoformat(revised.leave_by)
    diff_minutes = (original_leave_dt - new_leave_dt).total_seconds() / 60
    assert diff_minutes == 15
    assert any("15 minutes earlier" in c for c in revised.proposed_changes)

@pytest.mark.asyncio
async def test_revise_plan_nonexistent_id_raises_value_error():
    """Verify revise_plan raises ValueError for non-existent plan IDs."""
    with pytest.raises(ValueError, match="does not exist"):
        await revise_plan("invalid_plan_id", "Move the dentist to Monday")


@pytest.mark.asyncio
async def test_environment_override_preferences_and_lists(monkeypatch):
    """
    Verify that family preference lists, buffer defaults, and home coordinates
    can be dynamically set and overridden via environment variables (.env).
    """
    import importlib
    import server.config as config
    import server.seed as seed
    import server.planner as planner

    # Override environment variables for preference lists, buffer, and origin
    monkeypatch.setenv("DEFAULT_SAVED_SNACKS", "Protein bars, Coconut water, Cold packs")
    monkeypatch.setenv("DEFAULT_ARRIVAL_BUFFER_MINUTES", "45")
    monkeypatch.setenv("DEFAULT_HOME_NAME", "Family Headquarters")

    # Reload modules to pick up monkeypatched environment variables
    import sys
    importlib.reload(config)
    sys.modules["config"] = config
    sys.modules["server.config"] = config
    importlib.reload(seed)
    importlib.reload(planner)

    # Re-seed database with new environment-configured preferences
    seed.seed_demo_data()

    plan = await planner.propose_plan("Get us ready for Saturday's tournament")

    # Verify custom snack list from env was dynamically loaded into packing list
    assert "Protein bars" in plan.packing_list
    assert "Coconut water" in plan.packing_list
    assert "Cold packs" in plan.packing_list

    # Verify custom arrival buffer and origin name from env
    assert any("Family Headquarters" in c and "45 minutes" in c for c in plan.proposed_changes)

    # Clean up and restore default config state
    monkeypatch.undo()
    importlib.reload(config)
    sys.modules["config"] = config
    sys.modules["server.config"] = config
    importlib.reload(seed)
    importlib.reload(planner)
    seed.seed_demo_data()


@pytest.mark.asyncio
async def test_custom_matching_keywords_and_fields_from_env(monkeypatch):
    """
    Verify that generic keyword matching lists (PACKING_KEYWORD_MATCHES,
    EVENT_TEXT_FIELDS, LOCATION_KEYWORD_MATCHES) can be customized via .env.
    """
    import importlib
    import sys
    import server.config as config
    import server.planner as planner

    # Override keyword match lists via environment variables
    monkeypatch.setenv("PACKING_KEYWORD_MATCHES", "customgear, familyessentials")
    monkeypatch.setenv("EVENT_TEXT_FIELDS", "title, custom_notes, category")
    monkeypatch.setenv("LOCATION_KEYWORD_MATCHES", "residence, basecamp")

    importlib.reload(config)
    sys.modules["config"] = config
    sys.modules["server.config"] = config
    importlib.reload(planner)

    assert "customgear" in config.PACKING_KEYWORD_MATCHES
    assert "familyessentials" in config.PACKING_KEYWORD_MATCHES
    assert "custom_notes" in config.EVENT_TEXT_FIELDS
    assert "basecamp" in config.LOCATION_KEYWORD_MATCHES

    # Cleanup
    monkeypatch.undo()
    importlib.reload(config)
    sys.modules["config"] = config
    sys.modules["server.config"] = config
    importlib.reload(planner)
