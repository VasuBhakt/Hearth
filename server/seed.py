"""
Hearth Demo Data Seeder
Populates SQLite with Saturday tournament and dentist conflict demo data.
"""
from models import Event, Location
from db import (
    init_db,
    SessionLocal,
    EventModel,
    PreferenceModel,
    PlanCardModel,
    ApprovalTokenModel,
    UndoEntryModel,
    ChatMessageModel,
    save_event,
    set_preference,
)

def seed_demo_data() -> None:
    """Initialize database and seed reproducible demo data."""
    init_db(force=True)

    with SessionLocal() as session:
        # Wipe old data respecting FK constraints (children first)
        session.query(ChatMessageModel).delete()
        session.query(ApprovalTokenModel).delete()
        session.query(UndoEntryModel).delete()
        session.query(PlanCardModel).delete()
        session.query(EventModel).delete()
        session.query(PreferenceModel).delete()
        session.commit()

    # 1. Family Events (Using typed Pydantic models!)
    events = [
        Event(
            id="evt_tournament",
            title="Maya's Soccer Tournament",
            start_time="2026-10-17T09:00:00",
            end_time="2026-10-17T13:00:00",
            location=Location(
                name="Riverdale Regional Sports Complex",
                latitude=40.7128,
                longitude=-74.0060,
            ),
            attendees=["Maya", "Mom", "Dad"],
            description="Finals tournament. First match begins at 09:30.",
            priority=3,
            required_items=["Soccer uniform & cleats", "Shin guards & ball", "Water jug"],
        ),
        Event(
            id="evt_dentist",
            title="Maya's Dentist Appointment",
            start_time="2026-10-17T10:00:00",
            end_time="2026-10-17T11:00:00",
            location=Location(
                name="Bright Smiles Pediatric Clinic",
                latitude=40.7589,
                longitude=-73.9851,
            ),
            attendees=["Maya", "Mom"],
            description="Routine checkup and cleaning.",
            priority=1,
            required_items=["Insurance card"],
        ),
        Event(
            id="evt_groceries",
            title="Weekly Grocery Run",
            start_time="2026-10-16T17:30:00",
            end_time="2026-10-16T18:30:00",
            location=Location(
                name="Whole Foods Market",
                latitude=40.7282,
                longitude=-73.9942,
            ),
            attendees=["Dad"],
            description="Pick up weekly staples.",
            priority=1,
            required_items=["Reusable grocery bags"],
        ),
    ]

    for ev in events:
        save_event(ev)

    # 2. Saved Family Preferences (Seeded dynamically from .env configuration)
    from config import (
        DEFAULT_ARRIVAL_BUFFER_MINUTES,
        DEFAULT_HOME_NAME,
        DEFAULT_HOME_LATITUDE,
        DEFAULT_HOME_LONGITUDE,
        DEFAULT_SAVED_SNACKS,
        SCHEDULE_START_HOUR,
        SCHEDULE_END_HOUR,
    )
    set_preference("arrival_buffer_minutes", DEFAULT_ARRIVAL_BUFFER_MINUTES)
    set_preference("home_location", {
        "name": DEFAULT_HOME_NAME,
        "latitude": DEFAULT_HOME_LATITUDE,
        "longitude": DEFAULT_HOME_LONGITUDE,
    })
    set_preference("saved_snack_list", DEFAULT_SAVED_SNACKS)
    set_preference("schedule_start_hour", SCHEDULE_START_HOUR)
    set_preference("schedule_end_hour", SCHEDULE_END_HOUR)

    print("Success: SQLite database seeded with demo scenario at hearth.db!")

if __name__ == "__main__":
    seed_demo_data()
