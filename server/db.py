"""
Hearth SQLite Database Layer (SQLAlchemy 2.0)
High-performance relational schema:
- Composite/transient value objects (Location, WeatherForecast) are decomposed
  into native C-level binary columns (Float, Boolean, String) for maximum hardware performance.
- Relational integrity enforced via Foreign Keys and SQLite PRAGMA foreign_keys=ON.
- Security boundary: ApprovalTokens and UndoLedger entries strictly reference valid PlanCards.
"""
import os
from typing import Optional, List, Any
from sqlite3 import Connection as SQLite3Connection
from sqlalchemy import create_engine, String, Float, Boolean, JSON, Integer, ForeignKey, select, delete, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship

from models import (
    Event,
    Location,
    Preference,
    ConflictReport,
    WeatherForecast,
    PlanCard,
    ApprovalToken,
    UndoEntry,
)

try:
    from config import HEARTH_DB_PATH
except ImportError:
    HEARTH_DB_PATH = os.environ.get("HEARTH_DB_PATH", "hearth.db").strip('"').strip("'")

DATABASE_URL = f"sqlite:///{HEARTH_DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Enforce SQLite Foreign Key constraints on every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

class Base(DeclarativeBase):
    pass

# ============================================================================
# Optimized Relational Tables & Foreign Key Constraints
# ============================================================================

class EventModel(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)  # ISO 8601
    end_time: Mapped[str] = mapped_column(String, nullable=False)    # ISO 8601

    # Decomposed Location (Native C-level 8-byte Floats & Strings)
    location_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Collections
    attendees: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Event Priority & Required Gear
    priority: Mapped[int] = mapped_column(Integer, default=1)
    required_items: Mapped[list[str]] = mapped_column(JSON, default=list)

    def to_pydantic(self) -> Event:
        loc = None
        if self.location_name is not None:
            loc = Location(
                name=self.location_name,
                latitude=self.latitude if self.latitude is not None else 0.0,
                longitude=self.longitude if self.longitude is not None else 0.0,
            )
        return Event(
            id=self.id,
            title=self.title,
            start_time=self.start_time,
            end_time=self.end_time,
            location=loc,
            attendees=self.attendees or [],
            description=self.description,
            priority=self.priority,
            required_items=self.required_items or [],
        )

    @classmethod
    def from_pydantic(cls, event: Event) -> "EventModel":
        return cls(
            id=event.id,
            title=event.title,
            start_time=event.start_time,
            end_time=event.end_time,
            location_name=event.location.name if event.location else None,
            latitude=event.location.latitude if event.location else None,
            longitude=event.location.longitude if event.location else None,
            attendees=event.attendees,
            description=event.description,
            priority=event.priority,
            required_items=event.required_items,
        )


class PreferenceModel(Base):
    __tablename__ = "preferences"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)

    def to_pydantic(self) -> Preference:
        return Preference(key=self.key, value=self.value)

    @classmethod
    def from_pydantic(cls, pref: Preference) -> "PreferenceModel":
        return cls(key=pref.key, value=pref.value)


class PlanCardModel(Base):
    __tablename__ = "plan_cards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    target_date: Mapped[str] = mapped_column(String, nullable=False)
    leave_by: Mapped[str] = mapped_column(String, nullable=False)

    # Decomposed WeatherForecast (Native Floats, Booleans, Strings)
    weather_location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weather_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weather_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weather_condition: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weather_precip_chance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weather_wind_kph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weather_rain_warning: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Collections
    conflicts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    packing_list: Mapped[list[str]] = mapped_column(JSON, default=list)
    proposed_changes: Mapped[list[str]] = mapped_column(JSON, default=list)
    action_items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft")

    # Relationships
    approval_token: Mapped[Optional["ApprovalTokenModel"]] = relationship(
        "ApprovalTokenModel",
        back_populates="plan",
        cascade="all, delete-orphan",
        uselist=False,
    )
    undo_entries: Mapped[list["UndoEntryModel"]] = relationship(
        "UndoEntryModel",
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    def to_pydantic(self) -> PlanCard:
        conflicts_list = [ConflictReport(**c) for c in (self.conflicts or [])]

        weather_obj = None
        if self.weather_location is not None:
            weather_obj = WeatherForecast(
                location=self.weather_location,
                forecast_time=self.weather_time or "",
                temperature_c=self.weather_temp_c if self.weather_temp_c is not None else 0.0,
                weather_condition=self.weather_condition or "",
                precipitation_chance_percent=self.weather_precip_chance,
                wind_speed_kph=self.weather_wind_kph,
                rain_warning=bool(self.weather_rain_warning),
            )

        return PlanCard(
            id=self.id,
            title=self.title,
            target_date=self.target_date,
            leave_by=self.leave_by,
            conflicts=conflicts_list,
            weather=weather_obj,
            packing_list=self.packing_list or [],
            proposed_changes=self.proposed_changes or [],
            action_items=self.action_items or [],
            status=self.status,
        )

    @classmethod
    def from_pydantic(cls, plan: PlanCard) -> "PlanCardModel":
        w = plan.weather
        return cls(
            id=plan.id,
            title=plan.title,
            target_date=plan.target_date,
            leave_by=plan.leave_by,
            weather_location=w.location if w else None,
            weather_time=w.forecast_time if w else None,
            weather_temp_c=w.temperature_c if w else None,
            weather_condition=w.weather_condition if w else None,
            weather_precip_chance=w.precipitation_chance_percent if w else None,
            weather_wind_kph=w.wind_speed_kph if w else None,
            weather_rain_warning=w.rain_warning if w else None,
            conflicts=[c.model_dump() for c in plan.conflicts],
            packing_list=plan.packing_list,
            proposed_changes=plan.proposed_changes,
            action_items=plan.action_items,
            status=plan.status,
        )


class ApprovalTokenModel(Base):
    __tablename__ = "approval_tokens"

    # Foreign Key pointing directly to plan_cards.id with Cascade Delete
    plan_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("plan_cards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    token: Mapped[str] = mapped_column(String, nullable=False)
    approved_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)

    plan: Mapped["PlanCardModel"] = relationship(
        "PlanCardModel",
        back_populates="approval_token",
    )

    def to_pydantic(self) -> ApprovalToken:
        return ApprovalToken(
            plan_id=self.plan_id,
            token=self.token,
            approved_at=self.approved_at,
            expires_at=self.expires_at,
        )

    @classmethod
    def from_pydantic(cls, token: ApprovalToken) -> "ApprovalTokenModel":
        return cls(
            plan_id=token.plan_id,
            token=token.token,
            approved_at=token.approved_at,
            expires_at=token.expires_at,
        )


class UndoEntryModel(Base):
    __tablename__ = "undo_ledger"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Foreign Key pointing to the plan that initiated this change
    plan_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("plan_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    snapshot_data: Mapped[Any] = mapped_column(JSON, nullable=False)

    plan: Mapped["PlanCardModel"] = relationship(
        "PlanCardModel",
        back_populates="undo_entries",
    )

    def to_pydantic(self) -> UndoEntry:
        return UndoEntry(
            id=self.id,
            plan_id=self.plan_id,
            action_type=self.action_type,
            timestamp=self.timestamp,
            snapshot_data=self.snapshot_data,
        )

    @classmethod
    def from_pydantic(cls, entry: UndoEntry) -> "UndoEntryModel":
        return cls(
            id=entry.id,
            plan_id=entry.plan_id,
            action_type=entry.action_type,
            timestamp=entry.timestamp,
            snapshot_data=entry.snapshot_data,
        )


# ============================================================================
# Database Lifecycle & CRUD Helper Functions
# ============================================================================

def init_db(force: bool = False) -> None:
    """Create all SQLite tables if they do not exist. If force=True, drop existing tables first."""
    if force:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

# --- Event CRUD ---

def get_all_events() -> List[Event]:
    """Retrieve all calendar events ordered by start time."""
    with SessionLocal() as session:
        models = session.scalars(select(EventModel).order_by(EventModel.start_time)).all()
        return [m.to_pydantic() for m in models]

def get_event_by_id(event_id: str) -> Optional[Event]:
    """Retrieve an event by ID."""
    with SessionLocal() as session:
        model = session.get(EventModel, event_id)
        return model.to_pydantic() if model else None

def save_event(event: Event) -> None:
    """Insert or update a calendar event."""
    with SessionLocal() as session:
        existing = session.get(EventModel, event.id)
        new_data = EventModel.from_pydantic(event)
        if existing:
            existing.title = new_data.title
            existing.start_time = new_data.start_time
            existing.end_time = new_data.end_time
            existing.location_name = new_data.location_name
            existing.latitude = new_data.latitude
            existing.longitude = new_data.longitude
            existing.attendees = new_data.attendees
            existing.description = new_data.description
            existing.priority = new_data.priority
            existing.required_items = new_data.required_items
        else:
            session.add(new_data)
        session.commit()

def delete_event(event_id: str) -> bool:
    """Delete an event by ID. Returns True if deleted."""
    with SessionLocal() as session:
        model = session.get(EventModel, event_id)
        if model:
            session.delete(model)
            session.commit()
            return True
        return False

# --- Preferences CRUD ---

def get_preference(key: str, default: Any = None) -> Any:
    """Fetch stored preference value by key."""
    with SessionLocal() as session:
        pref = session.get(PreferenceModel, key)
        if pref:
            return pref.value
        return default

def set_preference(key: str, value: Any) -> None:
    """Save or update a preference setting."""
    with SessionLocal() as session:
        pref = session.get(PreferenceModel, key)
        if pref:
            pref.value = value
        else:
            session.add(PreferenceModel(key=key, value=value))
        session.commit()

def get_all_preferences() -> dict[str, Any]:
    """Retrieve all stored family preferences as a key-value dictionary."""
    with SessionLocal() as session:
        models = session.scalars(select(PreferenceModel)).all()
        return {m.key: m.value for m in models}

def delete_preference(key: str) -> bool:
    """Delete a stored preference by key."""
    with SessionLocal() as session:
        pref = session.get(PreferenceModel, key)
        if pref:
            session.delete(pref)
            session.commit()
            return True
        return False

# --- PlanCard CRUD ---

def save_plan(plan: PlanCard) -> None:
    """Save or update a draft or committed plan card."""
    with SessionLocal() as session:
        existing = session.get(PlanCardModel, plan.id)
        new_data = PlanCardModel.from_pydantic(plan)
        if existing:
            existing.title = new_data.title
            existing.target_date = new_data.target_date
            existing.leave_by = new_data.leave_by
            existing.weather_location = new_data.weather_location
            existing.weather_time = new_data.weather_time
            existing.weather_temp_c = new_data.weather_temp_c
            existing.weather_condition = new_data.weather_condition
            existing.weather_precip_chance = new_data.weather_precip_chance
            existing.weather_wind_kph = new_data.weather_wind_kph
            existing.weather_rain_warning = new_data.weather_rain_warning
            existing.conflicts = new_data.conflicts
            existing.packing_list = new_data.packing_list
            existing.proposed_changes = new_data.proposed_changes
            existing.action_items = new_data.action_items
            existing.status = new_data.status
        else:
            session.add(new_data)
        session.commit()

def get_plan(plan_id: str) -> Optional[PlanCard]:
    """Retrieve a plan card by ID."""
    with SessionLocal() as session:
        model = session.get(PlanCardModel, plan_id)
        return model.to_pydantic() if model else None

# --- Approval Token CRUD ---

def save_approval_token(token: ApprovalToken) -> None:
    """Store minted approval token."""
    with SessionLocal() as session:
        existing = session.get(ApprovalTokenModel, token.plan_id)
        new_data = ApprovalTokenModel.from_pydantic(token)
        if existing:
            existing.token = new_data.token
            existing.approved_at = new_data.approved_at
            existing.expires_at = new_data.expires_at
        else:
            session.add(new_data)
        session.commit()

def get_approval_token(plan_id: str) -> Optional[ApprovalToken]:
    """Retrieve approval token for a plan."""
    with SessionLocal() as session:
        model = session.get(ApprovalTokenModel, plan_id)
        return model.to_pydantic() if model else None

def verify_and_consume_token(plan_id: str, token: str) -> bool:
    """
    Validates the approval token:
    1. Verifies token exists and matches plan_id.
    2. Verifies token has not expired (TTL check).
    3. Burns (deletes) the token on success so it can never be replayed.
    Returns True if valid and consumed, False otherwise.
    """
    from datetime import datetime, timezone
    with SessionLocal() as session:
        record = session.get(ApprovalTokenModel, plan_id)
        if not record:
            return False  # No approval found

        if record.token != token:
            return False  # Forgery or wrong token

        now = datetime.now(timezone.utc).isoformat()
        if now > record.expires_at:
            session.delete(record)  # Clean up expired token
            session.commit()
            return False  # Expired!

        # Single-use security guarantee: Burn on use
        session.delete(record)
        session.commit()
        return True

# --- Undo Ledger CRUD ---

def save_undo_entry(entry: UndoEntry) -> None:
    """Append an action to the undo ledger and prune oldest entries beyond configured limit."""
    try:
        from config import UNDO_LEDGER_MAX_ENTRIES
    except ImportError:
        UNDO_LEDGER_MAX_ENTRIES = 50

    with SessionLocal() as session:
        session.add(UndoEntryModel.from_pydantic(entry))
        session.commit()

        # Prune oldest entries if exceeding configured limit
        all_entries = session.scalars(
            select(UndoEntryModel).order_by(UndoEntryModel.timestamp.desc())
        ).all()
        if len(all_entries) > UNDO_LEDGER_MAX_ENTRIES:
            for old in all_entries[UNDO_LEDGER_MAX_ENTRIES:]:
                session.delete(old)
            session.commit()


def get_latest_undo_entry() -> Optional[UndoEntry]:
    """Retrieve the most recent undo entry."""
    with SessionLocal() as session:
        model = session.scalars(
            select(UndoEntryModel).order_by(UndoEntryModel.timestamp.desc()).limit(1)
        ).first()
        return model.to_pydantic() if model else None

def get_undo_entry_by_plan(plan_id: str) -> Optional[UndoEntry]:
    """Retrieve the most recent undo entry for a specific plan."""
    with SessionLocal() as session:
        model = session.scalars(
            select(UndoEntryModel)
            .where(UndoEntryModel.plan_id == plan_id)
            .order_by(UndoEntryModel.timestamp.desc())
            .limit(1)
        ).first()
        return model.to_pydantic() if model else None

def delete_undo_entry(entry_id: str) -> bool:
    """Delete an undo entry after it has been consumed."""
    with SessionLocal() as session:
        entry = session.get(UndoEntryModel, entry_id)
        if entry:
            session.delete(entry)
            session.commit()
            return True
        return False