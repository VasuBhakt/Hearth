"""
Tests for Hearth Assistant Simulator API (server/simulator_api.py).
Validates HTML asset delivery, dynamic configuration, conversational orchestration,
approval token minting/commitment, surgical rollback, and scenario reset.
"""
import pytest
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

