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
    save_event,
    set_preference,
)

def seed_demo_data() -> None:
    """Initialize database and seed reproducible demo data."""
    init_db()

    with SessionLocal() as session:
        # Wipe old data respecting FK constraints (children first)
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
        ),
    ]

    for ev in events:
        save_event(ev)

    # 2. Saved Family Preferences
    set_preference("arrival_buffer_minutes", 30)
    set_preference("home_location", {
        "name": "Home",
        "latitude": 40.6782,
        "longitude": -73.9442,
    })
    set_preference("saved_snack_list", [
        "Orange slices",
        "Granola bars",
        "Electrolyte drinks",
        "Ice pack",
    ])

    print("Success: SQLite database seeded with demo scenario at hearth.db!")

if __name__ == "__main__":
    seed_demo_data()
