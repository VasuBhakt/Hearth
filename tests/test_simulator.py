"""
Tests for Hearth Assistant Simulator API (server/simulator_api.py).
Validates HTML asset delivery, dynamic configuration, conversational orchestration,
approval token minting/commitment, surgical rollback, and scenario reset.
"""
import pytest
import time
from fastapi.testclient import TestClient

from server.simulator_api import app
from server.config import (
    SIMULATOR_TITLE,
    DEFAULT_DEMO_SCENARIO_PROMPT,
    DEFAULT_PLAN_STATUS_DRAFT,
    DEFAULT_PLAN_STATUS_COMMITTED,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def deterministic_test_mode(monkeypatch):
    """Ensures automated tests use deterministic tool router without waiting on local LLM inference."""
    monkeypatch.setenv("LLM_PROVIDER", "fallback")



def test_serve_index_html():
    """Validates that the simulator root endpoint serves the single-page application."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "<title>Hearth — Family Assistant MCP Simulator</title>" in html
    assert "/static/css/tokens.css" in html
    assert "/static/css/base.css" in html
    assert "/static/js/app.js" in html


def test_get_simulator_config():
    """Validates runtime configuration endpoint populated from config.py and .env."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == SIMULATOR_TITLE
    assert data["default_prompt"] == DEFAULT_DEMO_SCENARIO_PROMPT
    assert data["protocol_version"] == "2026-07-28"
    assert data["min_protocol"] == "2025-11-25"
    assert data["draft_status"] == DEFAULT_PLAN_STATUS_DRAFT
    assert data["committed_status"] == DEFAULT_PLAN_STATUS_COMMITTED


def test_reset_scenario_database():
    """Validates that /api/reset restores SQLite demo events to clean state."""
    response = client.post("/api/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "reset" in data["message"].lower()


def test_chat_empty_message_validation():
    """Validates that empty user inputs are rejected with 400 Bad Request."""
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "error" in response.json()


def test_chat_propose_and_revise_flow():
    """Validates conversation orchestrator: proposing tournament plan and revising it."""
    # Reset first
    client.post("/api/reset")

    # 1. Propose plan
    res_prop = client.post(
        "/api/chat",
        json={"message": "Get us ready for Saturday's tournament"},
    )
    assert res_prop.status_code == 200
    data_prop = res_prop.json()
    assert "reply" in data_prop
    assert "plan" in data_prop
    plan = data_prop["plan"]
    assert plan is not None
    assert plan["status"] == DEFAULT_PLAN_STATUS_DRAFT
    plan_id = plan["id"]

    # 2. Revise plan
    res_rev = client.post(
        "/api/chat",
        json={"message": "Move the dentist to Monday", "plan_id": plan_id},
    )
    assert res_rev.status_code == 200
    data_rev = res_rev.json()
    revised_plan = data_rev["plan"]
    assert revised_plan is not None
    assert revised_plan["id"] == plan_id
    assert any("Monday" in ch for ch in revised_plan["proposed_changes"])


def test_approve_and_undo_flow():
    """Validates full security gate: minting token, committing plan, then surgical rollback."""
    # Reset first
    client.post("/api/reset")

    # Propose
    res_prop = client.post(
        "/api/chat",
        json={"message": "Get us ready for Saturday's tournament"},
    )
    plan_id = res_prop.json()["plan"]["id"]

    # Approve (Mints token and commits)
    res_app = client.post("/api/approve", json={"plan_id": plan_id})
    assert res_app.status_code == 200
    data_app = res_app.json()
    assert data_app["success"] is True
    assert data_app["commit"]["actions_executed"] >= 1
    assert data_app["plan"]["status"] == DEFAULT_PLAN_STATUS_COMMITTED

    # Undo (Surgically restores modified events and resets to draft)
    res_undo = client.post("/api/undo", json={"plan_id": plan_id})
    assert res_undo.status_code == 200
    data_undo = res_undo.json()
    assert data_undo["success"] is True
    assert data_undo["undo"]["restored_events_count"] >= 1
    assert data_undo["plan"]["status"] == DEFAULT_PLAN_STATUS_DRAFT


def test_cancel_plan_flow():
    """Validates that prompting to cancel/remove a plan discards the draft without re-proposing."""
    client.post("/api/reset")

    # Propose
    res_prop = client.post(
        "/api/chat",
        json={"message": "Get us ready for Saturday's tournament"},
    )
    assert res_prop.status_code == 200
    plan_id = res_prop.json()["plan"]["id"]

    # Cancel plan on prompt
    res_cancel = client.post(
        "/api/chat",
        json={"message": "cancel this plan", "plan_id": plan_id},
    )
    assert res_cancel.status_code == 200
    data_cancel = res_cancel.json()
    assert data_cancel["plan"] is None
    assert "cancelled" in data_cancel["message"].lower() or "cleared" in data_cancel["message"].lower()


def test_conflict_resolution_anchors_to_main_event():
    """Validates that conflict resolution anchors to the primary event, not the yielding event."""
    client.post("/api/reset")

    res = client.post(
        "/api/chat",
        json={"message": "Resolve schedule conflict: reschedule Dentist Appointment to free up Maya's Soccer Tournament"},
    )
    assert res.status_code == 200
    plan = res.json()["plan"]
    assert plan is not None
    # Must anchor to Maya's Soccer Tournament
    assert "Soccer" in plan["title"] or "Tournament" in plan["title"]
    # Must have a structured reschedule action for the Dentist (action_items are never humanized)
    assert any(
        a.get("action") == "reschedule_event" and "dentist" in a.get("event_title", "").lower()
        for a in plan["action_items"]
    ), "Expected a reschedule action_item for the Dentist appointment"
    # proposed_changes should reference dentist in some form after LLM humanization
    assert any("dentist" in ch.lower() for ch in plan["proposed_changes"])


def test_persistent_session_chat_history():
    """Validates that multi-turn chat dialogues persist to SQLite and survive cache clears."""
    from server.db import get_chat_history
    from server.simulator_api import _session_histories

    client.post("/api/reset")
    sess_id = "test-session-persistence-42"

    # 1. Send first message
    r1 = client.post("/api/chat", json={
        "message": "Get us ready for Saturday's tournament",
        "session_id": sess_id,
    })
    assert r1.status_code == 200

    # Verify directly from SQLite
    saved_history = get_chat_history(sess_id)
    assert len(saved_history) == 2
    assert saved_history[0]["role"] == "user"
    assert "Saturday" in saved_history[0]["content"]
    assert saved_history[1]["role"] == "assistant"

    # 2. Simulate server restart / memory wipe by clearing in-memory cache
    _session_histories.clear()

    # 3. Send second follow-up message with the same session_id
    r2 = client.post("/api/chat", json={
        "message": "Move the dentist to Monday",
        "session_id": sess_id,
        "plan_id": r1.json()["plan"]["id"],
    })
    assert r2.status_code == 200

    # Verify history now contains all 4 turns in SQLite
    updated_history = get_chat_history(sess_id)
    assert len(updated_history) == 4
    assert updated_history[2]["role"] == "user"
    assert "Monday" in updated_history[2]["content"]

    # 4. Reset scenario and verify history is purged
    client.post("/api/reset")
    assert len(get_chat_history(sess_id)) == 0


def test_cancel_disambiguates_by_date():
    """Validates that cancellation disambiguates multiple events with identical titles by specified date."""
    from server.db import save_event
    from server.models import Event, Location

    client.post("/api/reset")

    # Add a second dentist appointment on Monday, October 19, 2026
    oct19_dentist = Event(
        id="evt_dentist_oct19",
        title="Maya's Dentist Appointment",
        start_time="2026-10-19T09:00:00",
        end_time="2026-10-19T10:00:00",
        location=Location(name="Bright Smiles Pediatric Clinic", latitude=40.7128, longitude=-74.0060),
        attendees=["Maya", "Mom"],
        description="Follow-up dental checkup",
        priority=2,
    )
    save_event(oct19_dentist)

    # Prompt specifically to cancel October 19th appointment
    res = client.post("/api/chat", json={"message": "cancel the october 19th appointment"})
    assert res.status_code == 200
    plan = res.json()["plan"]
    assert plan is not None

    # Must target October 19th, NOT October 17th
    assert plan["target_date"] == "2026-10-19"
    assert any(
        a.get("action") == "delete_event" and a.get("event_id") == "evt_dentist_oct19"
        for a in plan["action_items"]
    ), f"Expected deletion of evt_dentist_oct19, got {plan['action_items']}"


def test_view_saved_event_details():
    """Validates querying and inspecting rich details of a saved calendar event."""
    client.post("/api/reset")

    res = client.post("/api/chat", json={"message": "Show details for Maya's soccer tournament"})
    assert res.status_code == 200
    data = res.json()

    assert "reply" in data
    assert data["event"] is not None
    ev = data["event"]

    assert "Soccer" in ev["title"] or "Tournament" in ev["title"]
    assert "attendees" in ev
    assert "Maya" in ev["attendees"]
    assert "required_items" in ev
    assert len(ev["required_items"]) > 0
    assert ev.get("duration_minutes", 0) > 0
    assert ev.get("location") is not None
    assert "Riverdale" in (ev["location"].get("name", "") if isinstance(ev["location"], dict) else "")
    # Should show the event card, not propose a replacement plan
    assert data["plan"] is None


def test_pronoun_followup_and_schedule_typo():
    """Validates pronoun resolution ('where is it?') and schedule queries with typo ('what are the event's scheduled?')."""
    client.post("/api/reset")
    sess_id = "test-session-followups-99"

    # 1. Ask about dentist appointment
    r1 = client.post("/api/chat", json={
        "message": "Show details for Maya's Dentist Appointment",
        "session_id": sess_id,
    })
    assert r1.status_code == 200
    assert r1.json()["event"] is not None

    # 2. Multi-turn follow-up: "where is it?"
    r2 = client.post("/api/chat", json={
        "message": "where is it?",
        "session_id": sess_id,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert "Dentist" in d2["reply"]
    assert "Bright Smiles" in d2["reply"]
    assert d2["event"] is not None

    # 3. Schedule question with apostrophe typo: "what are the event's scheduled?"
    r3 = client.post("/api/chat", json={
        "message": "what are the event's scheduled?",
        "session_id": sess_id,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["schedule"] is not None
    assert len(d3["schedule"]["events"]) >= 2
    assert "household schedule" in d3["reply"].lower()


def test_event_card_actions_weather_and_reschedule():
    """
    Validates:
    1. Weather forecast queries with specific venue & natural date work without crashes.
    2. Event Reschedule requests produce Reschedule PlanCards (not Cancel cards).
    3. Reschedule revisions with natural datetimes ('18th oct 2026 3 pm') update to the exact target slot.
    """
    client.post("/api/reset")
    sess_id = "test-card-actions-reschedule-weather-99"

    # 1. Weather forecast check
    rw = client.post("/api/chat", json={
        "message": "Weather forecast for Bright Smiles Pediatric Clinic on Sat, Oct 17, 2026",
        "session_id": sess_id,
    })
    assert rw.status_code == 200
    dw = rw.json()
    assert "error" not in dw["reply"].lower()
    assert ("Bright Smiles" in dw["reply"] or "forecast" in dw["reply"].lower() or "c" in dw["reply"].lower())

    # 2. Reschedule Dentist Appointment
    rr = client.post("/api/chat", json={
        "message": "Reschedule Maya's Dentist Appointment",
        "session_id": sess_id,
    })
    assert rr.status_code == 200
    dr = rr.json()
    plan = dr.get("plan")
    assert plan is not None, "Expected a draft reschedule plan"
    assert "Reschedule" in plan["title"], f"Expected Reschedule in title, got: {plan['title']}"
    assert not plan["title"].startswith("Cancel:")
    assert any(a.get("action") == "reschedule_event" for a in plan["action_items"])

    # 3. Follow-up: reschedule it on 18th oct 2026 3 pm
    rr2 = client.post("/api/chat", json={
        "message": "reschedule it on 18th oct 2026 3 pm",
        "plan_id": plan["id"],
        "session_id": sess_id,
    })
    assert rr2.status_code == 200
    dr2 = rr2.json()
    plan2 = dr2.get("plan")
    assert plan2 is not None
    assert "Reschedule" in plan2["title"]
    assert any(
        a.get("action") == "reschedule_event" and "2026-10-18T15:00:00" in a.get("new_start_time", "")
        for a in plan2["action_items"]
    ), f"Expected new_start_time to be 2026-10-18T15:00:00, got: {plan2['action_items']}"


def test_reschedule_with_destination_date_and_db_sync():
    """
    Tests that a natural reschedule request specifying source and destination dates
    (e.g., 'can reschedule maya's football tournament from 19th oct, to 17th oct, with the timings remaining same')
    generates a concrete reschedule plan targeting Oct 17 with 09:00 start time,
    commits cleanly to SQLite, and updates the live database schedule.
    """
    client = TestClient(app)
    sess_id = f"test_resched_sync_{int(time.time()*1000)}"

    resp = client.post("/api/chat", json={
        "message": "can reschedule maya's football tournament from 19th oct, to 17th oct, with the timings remaining same",
        "session_id": sess_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    plan = data.get("plan")
    assert plan is not None, f"Expected a draft plan, got response: {data}"
    assert "Reschedule" in plan["title"]
    assert plan["target_date"] == "2026-10-17"
    action = next((a for a in plan.get("action_items", []) if a.get("action") == "reschedule_event"), None)
    assert action is not None, f"Expected reschedule_event action item, got: {plan.get('action_items')}"
    assert "2026-10-17T09:00:00" in action.get("new_start_time", "")

    # Approve and commit plan via approval security gate
    app_resp = client.post("/api/approve", json={"plan_id": plan["id"]})
    assert app_resp.status_code == 200
    app_data = app_resp.json()
    assert app_data["success"] is True
    assert app_data["commit"]["actions_executed"] == 1

    # Check schedule now
    sched_resp = client.post("/api/chat", json={
        "message": "whats the schedule now",
        "session_id": sess_id,
    })
    assert sched_resp.status_code == 200
    sched_data = sched_resp.json()
    reply = sched_data.get("reply", "")
    assert "Oct 17, 2026" in reply or "Oct 17" in reply
    assert "draft changes haven't been applied yet" not in reply.lower()


def test_revise_plan_reschedule_with_time_range_and_departure_update():
    """
    Validates that revising an existing plan with:
    'can you reschedule the appointment on 19th oct to 17th oct, from 3pm to 4pm'
    correctly extracts 15:00-16:00, updates target_date to 2026-10-17,
    recalculates plan.leave_by for the 3pm start, and updates the departure strategy cleanly.
    """
    client = TestClient(app)
    client.post("/api/reset")
    sess_id = f"test_revise_timerange_{int(time.time()*1000)}"

    # 1. Propose initial plan
    prop_resp = client.post("/api/chat", json={
        "message": "Get us ready for Maya's dentist appointment",
        "session_id": sess_id,
    })
    assert prop_resp.status_code == 200
    plan = prop_resp.json().get("plan")
    assert plan is not None
    plan_id = plan["id"]

    # 2. Revise plan: move to 17th oct from 3pm to 4pm
    rev_resp = client.post("/api/chat", json={
        "message": "can you reschedule the appointment on 19th oct to 17th oct, from 3pm to 4pm",
        "plan_id": plan_id,
        "session_id": sess_id,
    })
    assert rev_resp.status_code == 200
    rev_plan = rev_resp.json().get("plan")
    assert rev_plan is not None
    assert rev_plan["target_date"] == "2026-10-17"
    assert "2026-10-17T14:" in rev_plan["leave_by"]

    action = next((a for a in rev_plan.get("action_items", []) if a.get("action") == "reschedule_event"), None)
    assert action is not None
    assert "2026-10-17T15:00:00" in action.get("new_start_time", "")
    assert "2026-10-17T16:00:00" in action.get("new_end_time", "")

    # Check strategy text does not contain ugly echoed raw strings like "to 19Th Oct To 17Th Oct"
    changes_text = " ".join(rev_plan.get("proposed_changes", []))
    assert "to 19Th Oct To 17Th Oct" not in changes_text
    assert "03:00 PM to 04:00 PM" in changes_text








