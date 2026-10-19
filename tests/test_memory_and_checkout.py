"""
Unit tests for Hearth's Memory & Provisioning Tools:
- remember_preference (cross-session memory 'same as last time')
- simulate_checkout (mock grocery/supply order staging behind safety boundary)
- End-to-end integration: saving preferences alters subsequent plan cards
"""
import pytest
from server.seed import seed_demo_data
from server.db import get_preference
from server.tools import remember_preference, simulate_checkout
from server.planner import propose_plan


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is seeded with demo scenario before each test."""
    seed_demo_data()


# ============================================================================
# 1. remember_preference Tests
# ============================================================================

def test_remember_preference_persists_data():
    """
    Verifies that calling remember_preference stores the preference into SQLite.
    """
    result = remember_preference("family_favorite_snacks", ["Dried mango", "Trail mix"])
    assert result["success"] is True
    assert result["key"] == "family_favorite_snacks"

    # Verify retrieval from database
    stored = get_preference("family_favorite_snacks")
    assert stored == ["Dried mango", "Trail mix"]


def test_remember_preference_normalizes_key():
    """
    Keys with mixed casing and spaces should be safely normalized to lowercase_snake_case.
    """
    result = remember_preference("Custom Departure Buffer", 40)
    assert result["success"] is True
    assert result["key"] == "custom_departure_buffer"
    assert get_preference("custom_departure_buffer") == 40


def test_remember_preference_empty_key_raises_error():
    """Empty or whitespace-only keys must be rejected."""
    with pytest.raises(ValueError, match="cannot be empty"):
        remember_preference("", ["item1"])

    with pytest.raises(ValueError, match="cannot be empty"):
        remember_preference("   ", ["item1"])


# ============================================================================
# 2. Cross-Session Memory Integration ("Same as last time")
# ============================================================================

@pytest.mark.asyncio
async def test_cross_session_memory_in_planning():
    """
    Verifies the 'same as last time' user journey:
    1. Parent previously saved preferred tournament snacks.
    2. A new planning session incorporates those saved preferences automatically into packing list.
    """
    # 1. Save new snacks in session 1
    remember_preference("tournament_snack_list", ["Electrolyte tablets", "Fig newtons"])

    # 2. Start session 2 (propose plan for Saturday)
    plan = await propose_plan("Get us ready for Saturday's tournament")

    # 3. Verify packing list dynamically picked up the cross-session preferences
    assert any("electrolyte" in item.lower() for item in plan.packing_list)
    assert any("fig newtons" in item.lower() for item in plan.packing_list)


# ============================================================================
# 3. simulate_checkout Tests
# ============================================================================

def test_simulate_checkout_creates_mock_order():
    """
    Verifies that simulate_checkout creates a staged mock order without payment processing.
    """
    items = ["Orange slices", "Electrolyte drinks", "Ice pack", "Sunscreen"]
    result = simulate_checkout(items=items, delivery_address="123 Oak Street")

    assert result["success"] is True
    assert "order_id" in result
    assert result["items"] == items
    assert result["item_count"] == 4
    assert result["delivery_destination"] == "123 Oak Street"
    assert result["status"] == "order_staged"
    assert "No payment" in result["message"] or "Zero payment" in result["message"]


def test_simulate_checkout_uses_default_home_address():
    """If no address is provided, falls back to .env configured home."""
    result = simulate_checkout(items=["Soccer shin guards"])
    assert result["success"] is True
    assert result["delivery_destination"] is not None
    assert result["item_count"] == 1


def test_simulate_checkout_empty_items_rejected():
    """Cannot checkout empty shopping list."""
    with pytest.raises(ValueError, match="empty list"):
        simulate_checkout(items=[])
