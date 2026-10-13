"""
Comprehensive unit tests for Hearth's 4 Read-Only Tools:
- get_context (validates dynamic preference addition, modification, and deletion)
- check_conflicts (validates overlap detection, tight gaps, and exact touching boundaries)
- estimate_travel (validates dynamic buffer adjustments and zero-distance edge cases)
- get_forecast (validates real API responses AND simulated network outage fallback)
"""
import pytest
from datetime import datetime, timedelta
import httpx

from server.seed import seed_demo_data
from server.models import Event, Location
from server.db import set_preference, delete_preference, save_event
from server.tools import (
    get_context,
    check_conflicts,
    estimate_travel,
    get_forecast,
)

@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is seeded with demo scenario before each test."""
    seed_demo_data()

# ============================================================================
# 1. get_context dynamic behavior tests
# ============================================================================

def test_get_context_returns_initial_seeded_data():
    """Verify get_context loads all initial events and seeded preferences."""
    ctx = get_context()
    assert "events" in ctx
    assert "preferences" in ctx
    assert len(ctx["events"]) >= 3

    prefs = ctx["preferences"]
    assert "arrival_buffer_minutes" in prefs
    assert "home_location" in prefs
    assert "saved_snack_list" in prefs

def test_get_context_dynamically_reflects_new_and_deleted_preferences():
    """
    Verify get_context dynamically loads new arbitrary preferences
    and reflects deletions with zero hardcoding.
    """
    # 1. Add brand new custom preferences at runtime
    set_preference("dietary_restrictions", ["gluten-free", "peanut-allergy"])
    set_preference("emergency_contact", "+1-555-0199")

    ctx_after_add = get_context()
    prefs = ctx_after_add["preferences"]
    assert "dietary_restrictions" in prefs
    assert prefs["dietary_restrictions"] == ["gluten-free", "peanut-allergy"]
    assert prefs["emergency_contact"] == "+1-555-0199"

    # 2. Delete a preference
    delete_preference("emergency_contact")
    ctx_after_delete = get_context()
    assert "emergency_contact" not in ctx_after_delete["preferences"]
    assert "dietary_restrictions" in ctx_after_delete["preferences"]


# ============================================================================
# 2. check_conflicts dynamic behavior & edge case tests
# ============================================================================

def test_check_conflicts_detects_dentist_tournament_clash():
    """Verify check_conflicts detects the direct overlap between tournament and dentist."""
    conflicts = check_conflicts()
    assert len(conflicts) >= 1

    overlap = next((c for c in conflicts if c.conflict_type == "Overlap"), None)
    assert overlap is not None
    assert "evt_tournament" in (overlap.event1_id, overlap.event2_id)
    assert "evt_dentist" in (overlap.event1_id, overlap.event2_id)

def test_check_conflicts_dynamically_adjusts_to_buffer_preference():
    """
    Verify that check_conflicts dynamically adapts to changes in
    arrival_buffer_minutes preference.
    """
    # Add two events on the same afternoon with a 45-minute gap between them
    e1 = Event(
        id="evt_practice",
        title="Soccer Practice",
        start_time="2026-10-18T14:00:00",
        end_time="2026-10-18T15:00:00",
        location=Location(name="Park", latitude=40.7, longitude=-74.0),
    )
    e2 = Event(
        id="evt_piano",
        title="Piano Lesson",
        start_time="2026-10-18T15:45:00",
        end_time="2026-10-18T16:30:00",
        location=Location(name="Studio", latitude=40.7, longitude=-74.0),
    )
    save_event(e1)
    save_event(e2)

    # 1. With buffer = 30 mins: 45 min gap is fine -> no Tight_Gap conflict
    set_preference("arrival_buffer_minutes", 30)
    conflicts_30 = check_conflicts()
    tight_gap_30 = [c for c in conflicts_30 if c.conflict_type == "Tight_Gap" and "evt_practice" in (c.event1_id, c.event2_id)]
    assert len(tight_gap_30) == 0

    # 2. Dynamically expand buffer to 60 mins: 45 min gap is now too tight!
    set_preference("arrival_buffer_minutes", 60)
    conflicts_60 = check_conflicts()
    tight_gap_60 = [c for c in conflicts_60 if c.conflict_type == "Tight_Gap" and "evt_practice" in (c.event1_id, c.event2_id)]
    assert len(tight_gap_60) == 1
    assert "less than the 60 min arrival buffer" in tight_gap_60[0].details

def test_check_conflicts_back_to_back_touching_boundary_is_tight_gap():
    """
    Edge case: Event A ends at 11:00 and Event B starts at exactly 11:00 (0-minute gap).
    This must NOT be marked as an Overlap, but MUST be flagged as Tight_Gap.
    """
    e1 = Event(
        id="evt_back1",
        title="Session 1",
        start_time="2026-10-19T10:00:00",
        end_time="2026-10-19T11:00:00",
        location=Location(name="Room A", latitude=40.7, longitude=-74.0),
    )
    e2 = Event(
        id="evt_back2",
        title="Session 2",
        start_time="2026-10-19T11:00:00",
        end_time="2026-10-19T12:00:00",
        location=Location(name="Room B", latitude=40.7, longitude=-74.0),
    )
    save_event(e1)
    save_event(e2)

    conflicts = check_conflicts()
    target = [c for c in conflicts if "evt_back1" in (c.event1_id, c.event2_id) and "evt_back2" in (c.event1_id, c.event2_id)]
    assert len(target) == 1
    assert target[0].conflict_type == "Tight_Gap"
    assert "0 min gap" in target[0].details


# ============================================================================
# 3. estimate_travel dynamic behavior & edge case tests
# ============================================================================

def test_estimate_travel_computes_distance_and_leave_by():
    """Verify estimate_travel calculates distance and departure time."""
    estimate = estimate_travel(
        origin_name="Home",
        origin_lat=40.6782,
        origin_lng=-73.9442,
        dest_name="Riverdale Regional Sports Complex",
        dest_lat=40.7128,
        dest_lng=-74.0060,
        target_arrival_time="2026-10-17T09:00:00",
    )
    assert estimate.distance_km > 0
    assert estimate.travel_time_minutes > 0
    assert estimate.recommended_leave_by < "2026-10-17T09:00:00"

def test_estimate_travel_dynamically_adjusts_to_buffer_preference():
    """
    Verify that increasing arrival buffer preference dynamically shifts
    the recommended leave-by time earlier by the exact delta.
    """
    # 30 min buffer
    set_preference("arrival_buffer_minutes", 30)
    est_30 = estimate_travel(
        origin_name="Home",
        origin_lat=40.6782,
        origin_lng=-73.9442,
        dest_name="Complex",
        dest_lat=40.7128,
        dest_lng=-74.0060,
        target_arrival_time="2026-10-17T09:00:00",
    )

    # 60 min buffer
    set_preference("arrival_buffer_minutes", 60)
    est_60 = estimate_travel(
        origin_name="Home",
        origin_lat=40.6782,
        origin_lng=-73.9442,
        dest_name="Complex",
        dest_lat=40.7128,
        dest_lng=-74.0060,
        target_arrival_time="2026-10-17T09:00:00",
    )

    t_30 = datetime.fromisoformat(est_30.recommended_leave_by)
    t_60 = datetime.fromisoformat(est_60.recommended_leave_by)

    # 60 min buffer must recommend leaving exactly 30 minutes earlier than 30 min buffer
    diff_minutes = (t_30 - t_60).total_seconds() / 60
    assert diff_minutes == 30.0

def test_estimate_travel_zero_distance_same_origin_destination():
    """
    Edge case: Origin and destination are identical coordinates (0 distance).
    Must not crash, must return 0 km, and must enforce minimum traffic buffer.
    """
    est = estimate_travel(
        origin_name="Home",
        origin_lat=40.6782,
        origin_lng=-73.9442,
        dest_name="Home Again",
        dest_lat=40.6782,
        dest_lng=-73.9442,
        target_arrival_time="2026-10-17T09:00:00",
    )
    assert est.distance_km == 0.0
    # Minimum driving time factor must be at least 10 minutes
    assert est.travel_time_minutes >= 10
    assert est.recommended_leave_by < "2026-10-17T09:00:00"


# ============================================================================
# 4. get_forecast real query AND simulated outage tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_forecast_returns_weather_data():
    """Verify get_forecast returns weather forecast with rain warning flag."""
    forecast = await get_forecast(
        location_name="Riverdale Regional Sports Complex",
        latitude=40.7128,
        longitude=-74.0060,
        date_str="2026-10-17",
    )
    assert forecast.location == "Riverdale Regional Sports Complex"
    assert forecast.forecast_time == "2026-10-17"
    assert isinstance(forecast.temperature_c, (int, float))
    assert isinstance(forecast.rain_warning, bool)

@pytest.mark.asyncio
async def test_get_forecast_offline_fallback_on_network_error(monkeypatch):
    """
    Edge case: Network timeout or connection drop.
    Proves that get_forecast does NOT raise an unhandled exception and
    gracefully triggers the bundled offline fallback forecast.
    """
    async def mock_network_timeout(*args, **kwargs):
        raise httpx.ConnectTimeout("Simulated Wi-Fi disconnect during live demo")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_network_timeout)

    # Must NOT raise exception; must return bundled fail-safe
    fallback = await get_forecast(
        location_name="Riverdale Regional Sports Complex",
        latitude=40.7128,
        longitude=-74.0060,
        date_str="2026-10-17",
    )
    assert fallback is not None
    assert fallback.location == "Riverdale Regional Sports Complex"
    assert fallback.rain_warning is True
    assert "Rain" in fallback.weather_condition
