"""
Hearth Data Models
Pydantic schemas for calendar events, preferences, reports, and forecasts.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field

"""
Value Objects. No database.
"""
class Location(BaseModel):
    name: str = Field(..., description = "location")
    latitude: float = Field(..., description="latitude")
    longitude: float = Field(..., description = "longitude")

class TravelEstimate(BaseModel):
    origin: str = Field(..., description = "Starting location name")
    destination: str = Field(..., description = "Destination location name")
    distance_km: float = Field(..., description = "Distance in kilometers")
    travel_time_minutes: int = Field(..., description = "Travel time in minutes")
    travel_mode: str = Field(..., description = "Mode of transport (e.g., 'driving')")
    recommended_leave_by: str = Field(..., description = "ISO time to leave")

class WeatherForecast(BaseModel):
    location: str = Field(..., description = "Location name")
    forecast_time: str = Field(..., description = "ISO time of forecast")
    temperature_c: float = Field(..., description = "Temperature in Celsius")
    weather_condition: str = Field(..., description = "Weather condition (e.g., 'Clear')")
    precipitation_chance_percent: Optional[float] = Field(None, description = "Probability percentage of precipitation (0-100)")
    wind_speed_kph: Optional[float] = Field(None, description = "Wind speed in kilometers per hour")
    rain_warning: bool = Field(default=False, description="True if rain is expected during outdoor events")

class ConflictReport(BaseModel):
    event1_id: str = Field(..., description="First event ID")
    event2_id: str = Field(..., description="Second event ID")
    conflict_type: str = Field(..., description = "Type of conflict: 'Overlap' or 'Tight_Gap'")
    details: str = Field(..., description="Detailed description of the conflict")
    
"""
Database Entities.
"""
class Event(BaseModel):
    id: str = Field(..., description = "Unique event ID")
    title: str = Field(..., description = "Event title")
    start_time: str = Field(..., description = "Start time in ISO format")
    end_time: str = Field(..., description = "End time in ISO format")
    location: Optional[Location] = Field(None, description = "Event location")
    attendees: List[str] = Field(default_factory=list, description="List of attendees")
    description: Optional[str] = Field(None, description="Additional details or notes")

class Preference(BaseModel):
    key: str = Field(..., description="Preference setting key") # acts as id
    value: Any = Field(..., description="Value associated with the preference")

class PlanCard(BaseModel):
    id: str = Field(..., description="Unique plan identifier")
    title: str = Field(..., description="E.g., 'Saturday Tournament Plan'")
    target_date: str = Field(..., description="Date of the event in ISO")
    leave_by: str = Field(..., description="Recommended departure time in ISO")
    conflicts: List[ConflictReport] = Field(default_factory=list, description="List of detected conflicts")
    weather: Optional[WeatherForecast] = Field(None, description="Weather forecast for the venue")
    packing_list: List[str] = Field(default_factory=list, description="Items to pack or buy")
    proposed_changes: List[str] = Field(default_factory=list, description="Human-readable summary of proposed actions")
    status: str = Field(default="draft", description="'draft', 'approved', or 'committed'")

class ApprovalToken(BaseModel):
    plan_id: str = Field(..., description="The ID of the plan being approved")
    token: str = Field(..., description="Cryptographic or UUID token minted strictly by user click")
    approved_at: str = Field(..., description="ISO timestamp of user approval")
    expires_at: str = Field(..., description="ISO timestamp when token expires")

class UndoEntry(BaseModel):
    id: str = Field(..., description="Unique undo transaction ID")
    plan_id: str = Field(..., description="Associated plan ID")
    action_type: str = Field(..., description="E.g., 'commit_plan'")
    timestamp: str = Field(..., description="Timestamp of when commit occurred")
    snapshot_data: Any = Field(..., description="Snapshot of previous state to restore")
