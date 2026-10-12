"""
Hearth MCP Server
Self-hosted Model Context Protocol server over Streamable HTTP transport.
Negotiates protocol version >=2025-11-25 for Alexa+ compliance.
"""

import os
import uvicorn
from mcp.server import MCPServer
from starlette.applications import Starlette

# Initialize Hearth MCP Server
mcp= MCPServer(
    name = "hearth-server",
    version = "0.1.0",
)

@mcp.tool(name = "ping", 
description = "Health check ping to verify server responsiveness")
async def ping() -> str:
    """Simple ping tool to verify MCP connection."""
    return "pong"

# Expose Starlette / ASGI app using streamable HTTP 
def create_app() -> Starlette:
    return mcp.streamable_http_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Starting Hearth MCP Server on port {port}...")
    uvicorn.run("mcp_server:create_app", 
        host = host,
        port = port,
        factory = True,
        reload = True
    )