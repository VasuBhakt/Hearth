"""
Hearth MCP Server
Self-hosted Model Context Protocol server over Streamable HTTP transport.
Negotiates protocol version >= 2025-11-25 for Alexa+ compliance.
Registers read-only and draft planning tools.
"""
import os
from typing import Dict, Any, List, Optional
import uvicorn
from mcp.server import MCPServer
from starlette.applications import Starlette

from tools import (
    get_context as fetch_context,
    check_conflicts as detect_conflicts,
    estimate_travel as calc_travel,
    get_forecast as fetch_forecast,
    remember_preference as save_preference,
    add_event as insert_event,
    remove_event as erase_event,
)
from planner import (
    propose_plan as generate_plan,
    revise_plan as update_plan,
    mint_approval_token as create_approval_token,
    commit_plan as execute_plan,
    undo_plan as rollback_plan,
)
from models import ConflictReport, TravelEstimate, WeatherForecast, PlanCard
from config import MCP_SERVER_NAME, MCP_SERVER_VERSION, DEFAULT_DEMO_SCENARIO_PROMPT

# Initialize Hearth MCP Server
mcp = MCPServer(
    name=MCP_SERVER_NAME,
    version=MCP_SERVER_VERSION,
)

@mcp.tool(name="ping", description="Health check ping to verify server responsiveness")
async def ping() -> str:
    """Simple ping tool to verify MCP connection."""
    return "pong"

@mcp.tool(name="get_context", description="Returns weekly calendar events and all saved family preferences")
async def get_context() -> Dict[str, Any]:
    """Fetch family context including all saved preferences."""
    return fetch_context()

@mcp.tool(name="check_conflicts", description="Finds overlapping events and tight gaps between activities")
async def check_conflicts() -> List[Dict[str, Any]]:
    """Scan calendar events for time conflicts."""
    conflicts = detect_conflicts()
    return [c.model_dump() for c in conflicts]

@mcp.tool(name="estimate_travel", description="Estimates driving time, distance, and recommended departure time")
async def estimate_travel(
    origin_name: str,
    origin_lat: float,
    origin_lng: float,
    dest_name: str,
    dest_lat: float,
    dest_lng: float,
    target_arrival_time: str,
) -> Dict[str, Any]:
    """Calculate travel route duration and leave-by time."""
    estimate = calc_travel(
        origin_name=origin_name,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_name=dest_name,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        target_arrival_time=target_arrival_time,
    )
    return estimate.model_dump()

@mcp.tool(name="get_forecast", description="Fetches weather forecast for a venue and date (Open-Meteo with offline fallback)")
async def get_forecast(
    location_name: str,
    latitude: float,
    longitude: float,
    date_str: str,
) -> Dict[str, Any]:
    """Fetch weather forecast and rain warnings for outdoor events."""
    forecast = await fetch_forecast(
        location_name=location_name,
        latitude=latitude,
        longitude=longitude,
        date_str=date_str,
    )
    return forecast.model_dump()

@mcp.tool(name="propose_plan", description="Generates a draft PlanCard addressing conflicts, weather, travel, and packing")
async def propose_plan(request: str = DEFAULT_DEMO_SCENARIO_PROMPT) -> Dict[str, Any]:
    """Builds a draft plan for preview without modifying calendar events."""
    plan = await generate_plan(request=request)
    return plan.model_dump()

@mcp.tool(name="revise_plan", description="Applies a spoken or typed adjustment to an existing draft PlanCard")
async def revise_plan(plan_id: str, instruction: str) -> Dict[str, Any]:
    """Applies adjustments to a draft plan card before approval."""
    updated = await update_plan(plan_id=plan_id, instruction=instruction)
    return updated.model_dump()

@mcp.tool(name="mint_approval_token", description="Simulates human UI approval by minting a single-use cryptographic token for a plan")
async def mint_approval_token(plan_id: str) -> Dict[str, Any]:
    """Generates an approval token representing human authorization."""
    token = create_approval_token(plan_id=plan_id)
    return token.model_dump()

@mcp.tool(name="commit_plan", description="Applies plan action items to calendar events with human approval security gate")
async def commit_plan(plan_id: str, approval_token: str) -> Dict[str, Any]:
    """Applies approved plan changes to the database and snapshots state in undo ledger."""
    return await execute_plan(plan_id=plan_id, approval_token=approval_token)

@mcp.tool(name="undo_plan", description="Rolls back calendar events to pre-commit snapshot and restores plan to draft")
async def undo_plan(plan_id: Optional[str] = None) -> Dict[str, Any]:
    """Reverts calendar mutations from an approved plan."""
    return await rollback_plan(plan_id=plan_id)

@mcp.tool(name="remember_preference", description="Persists a family preference setting (e.g. snack list, arrival buffer, origin) for cross-session recall")
async def remember_preference(key: str, value: Any) -> Dict[str, Any]:
    """Persist a preference setting for cross-session memory ('same as last time')."""
    return save_preference(key=key, value=value)

@mcp.tool(name="add_event", description="Add a new event or appointment to the household calendar and check for conflicts")
async def add_event(
    title: str,
    start_time: str,
    end_time: Optional[str] = None,
    location_name: Optional[str] = None,
    description: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    priority: int = 1,
) -> Dict[str, Any]:
    """Inserts a new event into the calendar and runs immediate conflict detection."""
    return insert_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        location_name=location_name,
        description=description,
        attendees=attendees,
        priority=priority,
    )

@mcp.tool(name="delete_event", description="Proposes cancelling an event or appointment from the calendar. Creates a draft plan card requiring human approval.")
async def delete_event(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a draft event cancellation plan card requiring human approval."""
    from planner import propose_event_cancellation
    plan = propose_event_cancellation(event_title=event_title, event_id=event_id, target_date=target_date)
    return plan.model_dump()


@mcp.tool(name="reschedule_event", description="Proposes moving or rescheduling an event or appointment. Creates a draft plan card requiring human approval.")
async def reschedule_event_tool(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
    target_datetime: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a draft event reschedule plan card requiring human approval."""
    from planner import propose_event_reschedule
    plan = propose_event_reschedule(event_title=event_title, event_id=event_id, target_datetime=target_datetime)
    return plan.model_dump()



@mcp.tool(name="get_event_details", description="Retrieves comprehensive details for a specific saved calendar event including attendees, priority, notes, gear checklist, and conflicts.")
async def get_event_details_tool(
    event_title: Optional[str] = None,
    event_id: Optional[str] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspects a specific calendar event in depth."""
    from tools import get_event_details
    return get_event_details(event_title=event_title, event_id=event_id, target_date=target_date)






# Expose Starlette / ASGI app using Streamable HTTP
def create_app() -> Starlette:
    return mcp.streamable_http_app()

if __name__ == "__main__":
    try:
        from config import PORT, HOST
    except ImportError:
        PORT = int(os.environ.get("PORT", 8000))
        HOST = os.environ.get("HOST", "127.0.0.1")
    print(f"Starting Hearth MCP Server on {HOST}:{PORT}...")
    uvicorn.run(
        "mcp_server:create_app",
        host=HOST,
        port=PORT,
        factory=True,
        reload=True,
    )