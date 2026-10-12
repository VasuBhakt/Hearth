# Hearth: Friction Log & Product Feedback

## Friction Log
*Record any issues, version discrepancies, or confusing errors encountered during development.*

| Date | Task attempted | Steps taken | Expected | Actual | Severity | Workaround | Suggestion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Oct 12, 2026 | Verify MCP SDK protocol version | Checked `mcp.types.LATEST_PROTOCOL_VERSION` on `mcp-2.3.0` | Support for `>=2025-11-25` | `LATEST_PROTOCOL_VERSION` is `2026-07-28` | Low | None needed, version clears requirement | Explicit compatibility table in SDK docs |

## Product Feedback
*Feedback for each tool, API, or SDK used (required by hackathon guidelines).*

### 1. Model Context Protocol (Python SDK)
- **Used for:** Implementing the self-hosted MCP server over Streamable HTTP transport.
- **What worked well:** Clean installation, modern async design.
- **What needs work:** Documentation around v1 vs v2 package renaming (`FastMCP` vs `MCPServer`) and protocol negotiation flags.
- **First hour experience:** Installed smoothly, verified protocol capabilities.
- **Would build with it again:** Yes.
