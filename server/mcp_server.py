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
    simulate_checkout as mock_checkout,
)
from planner import (
    propose_plan as generate_plan,
    revise_plan as update_plan,
    mint_approval_token as create_approval_token,
    commit_plan as execute_plan,
    undo_plan as rollback_plan,
)
from models import ConflictReport, TravelEstimate, WeatherForecast, PlanCard

# Initialize Hearth MCP Server
mcp = MCPServer(
    name="hearth-server",
    version="0.1.0",
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
async def propose_plan(request: str = "Get us ready for Saturday's tournament") -> Dict[str, Any]:
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

@mcp.tool(name="simulate_checkout", description="Simulates creating a mock provisioning order from a packing or shopping list (zero payment processing)")
async def simulate_checkout(items: List[str], delivery_address: Optional[str] = None) -> Dict[str, Any]:
    """Simulates ordering supplies from a packing list without taking payment info."""
    return mock_checkout(items=items, delivery_address=delivery_address)



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