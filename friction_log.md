# Hearth: Friction Log & Product Feedback

> **Submission Document for Amazon App Dev 2026 Hackathon**  
> *Tracked across the build cycle (Oct 12 – Oct 23, 2026).*

---

## 📋 Friction Log

| Date | Task Attempted | Steps Taken | Expected | Actual | Severity | Workaround | Concrete Suggestion |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Oct 12** | Verify MCP Python SDK protocol version | Checked `mcp.types.LATEST_PROTOCOL_VERSION` on `mcp-2.3.0` | Support for `>=2025-11-25` | `LATEST_PROTOCOL_VERSION` is `2026-07-28` | Low | None needed; version clears requirement. | Provide an explicit compatibility/version matrix table in SDK docs. |
| **Oct 14** | FastMCP ASGI Mounting | Attempted to mount MCP server endpoint under FastAPI using `mcp.asgi` | Standard ASGI sub-application routing | Version 2.x renamed `FastMCP` to `MCPServer` with breaking transport changes | Medium | Implemented a unified FastAPI SSE streaming router exposing JSON-RPC `/messages` and `/sse`. | Maintain backward compatibility aliases during major SDK refactors. |
| **Oct 16** | Open-Meteo City Query | Queried Open-Meteo forecast directly with city names (`"Kolkata"`, `"New York"`) | Forecast data returned for named locations | API rejected text queries (requires numeric `latitude` and `longitude`) | Medium | Integrated Open-Meteo's free geocoding API endpoint to dynamically resolve city names to coordinates. | Add a convenience endpoint on Open-Meteo that accepts `?city=...` directly. |
| **Oct 18** | Groq Turn 2 Tool Calling | Chained multi-turn tool conversations with Groq's `chat/completions` API | Model processes tool result and produces final user response | HTTP 400 (`"Tool choice is none, but model called a tool"`) | High | Explicitly sanitized turn-2 payload: omitted `tools` when feeding final tool output back to model. | Align Groq error messages and empty payload handling closer to native OpenAI specs. |
| **Oct 20** | Groq Daily Token Limits | Tested repeated planning workflows during video demo prep | Seamless cloud LLM inference | 429 Too Many Requests (daily free tier TPM/RPD exhausted) | High | Engineered a zero-dependency offline Smart Tool Router (`LLM_PROVIDER="fallback"`) with 0ms network latency. | Provide clearer dev console dashboard alerts before hitting daily ceiling. |
| **Oct 21** | Natural Language Date Range Parsing | Parsed `"from 19th oct to 17th oct, with timings remaining same"` | New date set to Oct 17; event time preserved | Regex greedily matched Oct 19 (source) rather than Oct 17 (destination) | High | Built a two-pass parser: detects `<source> to <destination>` patterns and extracts destination bounds. | Standardize natural language date resolution helper utilities in MCP tool libraries. |
| **Oct 23** | Complex Time Range Rescheduling | Rescheduled event with prompt: `"from 8:05 pm to 24th october 2026 6:30 pm"` | Start time shifted to 6:30 PM | Parser seized on `8:05 pm` (first time token) instead of target `6:30 pm` | High | Re-engineered `parse_natural_datetime` to isolate destination string after the `to` boundary. | Provide pre-tested datetime intent grammar in agent starter kits. |
| **Oct 23** | Docker Environment Ingestion | Ran containerized Hearth simulator via Docker Compose | All `.env` API keys and parameters loaded into container | Container started without host `.env` values unless explicitly declared | Medium | Added `env_file: - .env` to `docker-compose.yml` and wildcard `COPY .env* ./` to `Dockerfile`. | Docker Compose could default to loading local `.env` if no `env_file` is specified. |

---

## 🛠️ Product Feedback

### 1. Model Context Protocol (Python SDK)
* **What did you use it for?** Implementing the core Hearth domain server tools (`get_context`, `check_conflicts`, `get_forecast`, `estimate_travel`, `propose_plan`, `revise_plan`, `reschedule_event`).
* **What worked well:** Strongly-typed function signatures, clean async ergonomics, and native interoperability with modern LLM function-calling protocols.
* **What needs work:** Major version transitions (v1 `FastMCP` to v2 `MCPServer`) caused confusion in ecosystem tutorials. Documentation around streamable HTTP transport vs SSE needs more complete end-to-end examples.
* **How was the first hour?** Fast and intuitive for basic tool declarations; required source code inspection to understand the ASGI mount lifecycle.
* **Would you build with it again?** **Yes.** It is the most robust and structured abstraction for domain tool exposure currently available.

---

### 2. AWS Bedrock & Amazon Nova
* **What did you use it for?** Production LLM orchestration, natural language plan humanization, and intent resolution.
* **What worked well:** Low latency, clean AWS SDK integration, reliable JSON output modes, and predictable function calling behavior.
* **What needs work:** IAM permissions and cross-region model access requirements can be intimidating for rapid hackathon setup compared to simple bearer-token endpoints.
* **How was the first hour?** Setting up AWS credentials and Bedrock model access took ~30 minutes; once IAM policies were verified, requests ran smoothly.
* **Would you build with it again?** **Yes.** High enterprise reliability and predictable uptime make it ideal for family data systems.

---

### 3. Groq Cloud API
* **What did you use it for?** Ultra-fast multi-turn conversational agent prototyping using Llama 3.3 70B.
* **What worked well:** Lightning-fast inference speeds (sub-500ms time-to-first-token), making interactive voice/chat feel instantaneous.
* **What needs work:** Strict daily free tier limits can halt hackathon testing abruptly without warning. Turn-2 tool calling payloads require strict formatting.
* **How was the first hour?** Superb — hello-world took less than 5 minutes with a standard OpenAI-compatible client.
* **Would you build with it again?** **Yes**, for prototyping and demo speed, backed by an offline fallback.

---

### 4. Open-Meteo API
* **What did you use it for?** Hyper-local weather forecasting (precipitation probability, temperatures, weather codes) to automatically adapt family packing checklists (rain jackets, umbrellas).
* **What worked well:** Zero API key requirement, generous rate limits, sub-100ms response times, and rich daily metric fields.
* **What needs work:** Requires coordinates rather than place names (necessitating a separate geocoding call).
* **How was the first hour?** 10 minutes to query and verify temperature and rain warnings.
* **Would you build with it again?** **Yes, 100%.** The best developer-friendly weather API available today.

---

### 5. FastAPI & Uvicorn
* **What did you use it for?** Serving the Hearth Simulator Web UI, approval tokens, undo ledger APIs, and static assets.
* **What worked well:** Auto-reloading during development, automatic OpenAPI schema generation, and high async concurrency.
* **What needs work:** Nothing significant — battle-tested and rock solid.
* **How was the first hour?** 5 minutes from `pip install` to live endpoints.
* **Would you build with it again?** **Yes.** The undisputed standard for modern Python web services.

---

## 💡 Feature Requests

1. **MCP Client SDK — Standardized Proposal Card Schema**
   * *Description:* A first-class specification for staging draft actions before tool execution.
   * *Why it matters:* Prevents autonomous agents from causing silent calendar corruption and provides a unified UI pattern for human approval.
   * *Priority:* **Critical**

2. **Open-Meteo — Natural Place Name Resolution**
   * *Description:* Allow passing `?city=Seattle` or `?location=Central+Park` directly to the `/forecast` endpoint.
   * *Why it matters:* Eliminates redundant roundtrips to the geocoding service.
   * *Priority:* **Nice-to-have**
