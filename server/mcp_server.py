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
)
from models import ConflictReport, TravelEstimate, WeatherForecast

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

# Expose Starlette / ASGI app using Streamable HTTP
def create_app() -> Starlette:
    return mcp.streamable_http_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Starting Hearth MCP Server on port {port}...")
    uvicorn.run(
        "mcp_server:create_app",
        host=host,
        port=port,
        factory=True,
        reload=True,
    )