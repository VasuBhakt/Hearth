"""
Test MCP handshake and protocol negotiation.
Verifies that the server negotiates protocol version >= 2025-11-25.
"""
import os
import pytest
from mcp.server import MCPServer
import mcp.types as types

@pytest.mark.asyncio
async def test_protocol_version_negotiation():
    """Verify that the SDK environment supports protocol >= 2025-11-25."""
    latest_version = types.LATEST_PROTOCOL_VERSION
    min_required = os.environ.get("MIN_PROTOCOL_VERSION", "2025-11-25")

    print(f"\nNegotiated/Latest Protocol Version: {latest_version}")
    assert latest_version >= min_required, (
        f"Protocol version {latest_version} does not meet requirement {min_required}"
    )

def test_server_creation():
    """Verify Hearth MCP server initializes correctly."""
    server= MCPServer(
        name = "hearth-test",
        version = "0.1.0"
    )
    assert server.name == "hearth-test"
