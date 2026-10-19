"""
Unit tests for Hearth's Security Gate, Commit, and Undo Ledger:
- Rejection of commit without valid token
- Rejection of forged or expired tokens
- Successful commit applies calendar mutations and burns approval token (single-use guarantee)
- Replay attack prevention (consumed token cannot be used again)
- Exact state rollback via undo_plan (restores prior calendar events and resets plan to draft)
- Undo entry deletion upon consumption (cannot undo twice)
- Configurable settings via environment (.env)
"""
import pytest
from datetime import datetime, timezone, timedelta
from server.seed import seed_demo_data
from server.models import Event, ApprovalToken, UndoEntry
from server.db import (
    get_all_events,
    get_event_by_id,
    get_plan,
    save_approval_token,
    get_approval_token,
    get_undo_entry_by_plan,
    get_latest_undo_entry,
    save_undo_entry,
)
from server.planner import (
    propose_plan,
    revise_plan,
    mint_approval_token,
    commit_plan,
    undo_plan,
)
from server.config import (
    DEFAULT_PLAN_STATUS_DRAFT,
    DEFAULT_PLAN_STATUS_COMMITTED,
    ACTION_TYPE_COMMIT_PLAN,
    APPROVAL_TOKEN_TTL_MINUTES,
    UNDO_LEDGER_MAX_ENTRIES,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is seeded with demo scenario before each test."""
    seed_demo_data()


# ============================================================================
# 1. Approval Security Gate Tests
# ============================================================================

@pytest.mark.asyncio
async def test_commit_plan_without_token_rejected():
    """
    CRITICAL SECURITY GATE:
    An AI agent or caller cannot execute a plan without providing a token.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")

    with pytest.raises(ValueError, match="Missing approval token"):
        await commit_plan(plan.id, "")

    with pytest.raises(ValueError, match="Missing approval token"):
        await commit_plan(plan.id, "   ")


@pytest.mark.asyncio
async def test_commit_plan_with_invalid_token_rejected():
    """
    Forged or nonexistent tokens must be immediately rejected.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")

    with pytest.raises(ValueError, match="Invalid or expired approval token"):
        await commit_plan(plan.id, "forged_malicious_token_xyz")


@pytest.mark.asyncio
async def test_commit_plan_with_expired_token_rejected():
    """
    Expired tokens must be rejected and cleaned up.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")

    # Manually mint a token that expired in the past
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    expired_token = ApprovalToken(
        plan_id=plan.id,
        token="expired_token_abc",
        approved_at=(datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat(),
        expires_at=past_time,
    )
    save_approval_token(expired_token)

    with pytest.raises(ValueError, match="Invalid or expired approval token"):
        await commit_plan(plan.id, "expired_token_abc")

    # Verify the expired token was pruned from the database
    assert get_approval_token(plan.id) is None


# ============================================================================
# 2. Successful Commit & Token Burn (Single-Use Guarantee)
# ============================================================================

@pytest.mark.asyncio
async def test_commit_plan_success_and_token_burned():
    """
    Verifies that:
    1. Valid token commits the plan.
    2. Calendar event is mutated in database.
    3. Plan status becomes 'committed'.
    4. Token is burned (cannot be queried again).
    5. Undo entry is created.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")
    assert plan.status == DEFAULT_PLAN_STATUS_DRAFT

    # Find the conflicting event ID (the dentist appointment)
    dentist_event_before = get_event_by_id("evt_dentist")
    assert dentist_event_before is not None
    original_start = dentist_event_before.start_time

    # Mint authorization token (simulates UI 'Approve' click)
    token = mint_approval_token(plan.id)
    assert token.plan_id == plan.id
    assert len(token.token) > 20

    # Commit the plan
    result = await commit_plan(plan.id, token.token)
    assert result["success"] is True
    assert result["status"] == DEFAULT_PLAN_STATUS_COMMITTED
    assert result["actions_executed"] >= 1

    # Verify calendar mutation occurred in the database
    dentist_event_after = get_event_by_id("evt_dentist")
    assert dentist_event_after.start_time != original_start

    # Verify plan status updated in database
    db_plan = get_plan(plan.id)
    assert db_plan.status == DEFAULT_PLAN_STATUS_COMMITTED

    # Verify SINGLE-USE guarantee: Token is burned immediately
    assert get_approval_token(plan.id) is None

    # Verify undo ledger contains a record for this commit
    undo_entry = get_undo_entry_by_plan(plan.id)
    assert undo_entry is not None
    assert undo_entry.action_type == ACTION_TYPE_COMMIT_PLAN


@pytest.mark.asyncio
async def test_commit_plan_token_replay_rejected():
    """
    Replay attack prevention: A token that has already been consumed cannot be re-used.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")
    token = mint_approval_token(plan.id)

    # First commit succeeds
    result = await commit_plan(plan.id, token.token)
    assert result["success"] is True

    # Second commit with the same token MUST fail
    with pytest.raises(ValueError, match="already been committed"):
        await commit_plan(plan.id, token.token)


# ============================================================================
# 3. Exact State Rollback via undo_plan
# ============================================================================

@pytest.mark.asyncio
async def test_undo_plan_restores_exact_prior_state():
    """
    Verifies that calling undo_plan:
    1. Restores all calendar events to their exact pre-commit timestamps.
    2. Resets the plan status back to 'draft'.
    3. Deletes the consumed undo record from the ledger.
    """
    # Capture original calendar snapshot
    events_initial = get_all_events()
    dentist_initial = get_event_by_id("evt_dentist")
    initial_start = dentist_initial.start_time

    # Generate, approve, and commit plan
    plan = await propose_plan("Get us ready for Saturday's tournament")
    token = mint_approval_token(plan.id)
    await commit_plan(plan.id, token.token)

    # Verify the event was moved
    dentist_moved = get_event_by_id("evt_dentist")
    assert dentist_moved.start_time != initial_start

    # Execute Undo
    undo_result = await undo_plan(plan.id)
    assert undo_result["success"] is True
    assert undo_result["status"] == DEFAULT_PLAN_STATUS_DRAFT

    # Verify event is restored EXACTLY to its original start time
    dentist_restored = get_event_by_id("evt_dentist")
    assert dentist_restored.start_time == initial_start

    # Verify all events match initial count and times
    events_restored = get_all_events()
    assert len(events_restored) == len(events_initial)
    assert {e.id: (e.start_time, e.end_time) for e in events_restored} == {
        e.id: (e.start_time, e.end_time) for e in events_initial
    }

    # Verify plan status in database is reset to 'draft'
    db_plan = get_plan(plan.id)
    assert db_plan.status == DEFAULT_PLAN_STATUS_DRAFT

    # Verify the consumed undo entry is removed
    assert get_undo_entry_by_plan(plan.id) is None


@pytest.mark.asyncio
async def test_undo_plan_without_entry_raises_error():
    """
    Attempting to undo a plan with no recorded undo snapshot raises an error.
    """
    with pytest.raises(ValueError, match="No undo record found"):
        await undo_plan("nonexistent_plan_id")


@pytest.mark.asyncio
async def test_undo_plan_latest_when_no_plan_id_specified():
    """
    Calling undo_plan() without plan_id rolls back the most recent commit.
    """
    dentist_initial = get_event_by_id("evt_dentist")
    initial_start = dentist_initial.start_time

    plan = await propose_plan("Get us ready for Saturday's tournament")
    token = mint_approval_token(plan.id)
    await commit_plan(plan.id, token.token)

    # Verify mutated
    assert get_event_by_id("evt_dentist").start_time != initial_start

    # Undo without arguments
    undo_result = await undo_plan()
    assert undo_result["success"] is True

    # Restored
    assert get_event_by_id("evt_dentist").start_time == initial_start


@pytest.mark.asyncio
async def test_undo_prior_plan_does_not_affect_subsequent_plan():
    """
    Surgical Undo Guarantee:
    If Plan 1 modifies Event A and Plan 2 modifies Event B:
    Undoing Plan 1 must restore Event A WITHOUT touching Event B from Plan 2.
    """
    from server.models import Location, PlanCard
    from server.db import save_event, save_plan

    # 1. Setup initial events
    dentist_initial = get_event_by_id("evt_dentist")
    dentist_orig_start = dentist_initial.start_time

    piano_initial = Event(
        id="evt_piano_lesson",
        title="Leo's Piano Lesson",
        start_time="2026-10-18T15:00:00",
        end_time="2026-10-18T16:00:00",
        location=Location(name="Music Studio", latitude=40.71, longitude=-74.0),
        priority=1,
    )
    save_event(piano_initial)

    # 2. Plan 1: Tournament plan moves dentist
    plan1 = await propose_plan("Get us ready for Saturday's tournament")
    token1 = mint_approval_token(plan1.id)
    await commit_plan(plan1.id, token1.token)

    # Verify dentist was moved
    dentist_after_p1 = get_event_by_id("evt_dentist")
    assert dentist_after_p1.start_time != dentist_orig_start

    # 3. Plan 2: Moves piano lesson to 17:00
    plan2 = PlanCard(
        id="plan_piano_shift",
        title="Shift Piano Lesson",
        target_date="2026-10-18",
        leave_by="2026-10-18T16:30:00",
        action_items=[
            {
                "action": "reschedule_event",
                "event_id": "evt_piano_lesson",
                "event_title": "Leo's Piano Lesson",
                "new_start_time": "2026-10-18T17:00:00",
                "new_end_time": "2026-10-18T18:00:00",
            }
        ],
        status="draft",
    )
    save_plan(plan2)
    token2 = mint_approval_token(plan2.id)
    await commit_plan(plan2.id, token2.token)

    # Verify piano lesson was moved to 17:00
    piano_after_p2 = get_event_by_id("evt_piano_lesson")
    assert piano_after_p2.start_time == "2026-10-18T17:00:00"

    # 4. SURGICAL UNDO: Undo Plan 1 (the older plan)
    undo_res1 = await undo_plan(plan1.id)
    assert undo_res1["success"] is True

    # 5. Verify Event A (Dentist) is restored to its original time
    dentist_restored = get_event_by_id("evt_dentist")
    assert dentist_restored.start_time == dentist_orig_start

    # 6. CRITICAL CHECK: Event B (Piano lesson) from Plan 2 MUST STILL BE AT 17:00!
    piano_check = get_event_by_id("evt_piano_lesson")
    assert piano_check.start_time == "2026-10-18T17:00:00"

    # 7. Undo Plan 2 restores Piano lesson back to 15:00
    undo_res2 = await undo_plan(plan2.id)
    assert undo_res2["success"] is True
    assert get_event_by_id("evt_piano_lesson").start_time == "2026-10-18T15:00:00"


# ============================================================================
# 4. Revise and Commit Flow
# ============================================================================


@pytest.mark.asyncio
async def test_revise_plan_then_commit_executes_revised_action():
    """
    Verify that revising a plan ('Move the dentist to Monday') updates the action items,
    and committing applies the revised Monday slot to the database.
    """
    plan = await propose_plan("Get us ready for Saturday's tournament")
    revised = await revise_plan(plan.id, "Move the dentist to Monday")

    token = mint_approval_token(revised.id)
    await commit_plan(revised.id, token.token)

    dentist_event = get_event_by_id("evt_dentist")
    assert dentist_event is not None
    dt = datetime.fromisoformat(dentist_event.start_time)
    # Weekday 0 is Monday
    assert dt.weekday() == 0


# ============================================================================
# 5. Undo Ledger Pruning
# ============================================================================

def test_undo_ledger_max_entries_pruning():
    """
    Verify that save_undo_entry prunes older records when exceeding UNDO_LEDGER_MAX_ENTRIES.
    """
    from server.models import PlanCard
    from server.db import save_plan

    plan_id = "test_plan_prune"
    save_plan(
        PlanCard(
            id=plan_id,
            title="Pruning Test Plan",
            target_date="2026-10-19",
            leave_by="2026-10-19T08:00:00",
        )
    )

    # Seed entries up to the limit + 5
    for i in range(UNDO_LEDGER_MAX_ENTRIES + 5):
        entry = UndoEntry(
            id=f"undo_test_{i:03d}",
            plan_id=plan_id,
            action_type="test_action",
            timestamp=(datetime.now(timezone.utc) + timedelta(seconds=i)).isoformat(),
            snapshot_data=[],
        )
        save_undo_entry(entry)

    # Query all entries
    from server.db import SessionLocal, UndoEntryModel, select
    with SessionLocal() as session:
        entries = session.scalars(select(UndoEntryModel)).all()
        assert len(entries) <= UNDO_LEDGER_MAX_ENTRIES
