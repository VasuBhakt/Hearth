# 🏠 Hearth

> Built for the [Amazon App Dev 2026](https://amazonappdev2026.devpost.com/) Hackathon. Designed for **AWS Bedrock (Amazon Nova)** and local **Model Context Protocol (MCP)** execution.

A local family coordination assistant built with Python, FastAPI, and the Model Context Protocol (MCP). It handles event scheduling, conflict checks, venue weather forecasts, and travel time estimates.

Unlike agents that directly modify calendar databases, Hearth drafts changes into a proposal card first. The database is only updated when you click approve. An undo ledger records modified events so changes can be reverted.

---

## ⚙️ How It Works

1. 💬 **Natural Language Requests**: You send a request through the web UI or chat API (e.g. asking to prepare for an event or reschedule one).
2. 🛠️ **MCP Tool Execution**: The backend calls domain tools to gather context:
   - Calendar events from SQLite (`hearth.db`)
   - Schedule conflicts between family members
   - Weather forecast for the venue via Open-Meteo
   - Driving travel time and departure buffers via Haversine calculations
3. 📋 **Draft Proposal**: The server returns a proposal card containing:
   - Recommended leave-by time
   - Packing checklist (including weather-adapted items like rain gear)
   - Proposed schedule adjustments to resolve conflicts
4. 🔒 **Approval & Commit**:
   - The user clicks **Approve** on the proposal card.
   - The server verifies an approval token and applies the updates to SQLite.
   - A snapshot of affected events is stored in an undo ledger.
5. ↩️ **Rollback & Undo**:
   - Clicking **Undo** restores the modified events to their exact state prior to approval.

---

## 🚀 Setup and Running

### 1. Requirements
* Python 3.10+
* Git

### 2. Install Dependencies
```bash
git clone https://github.com/VasuBhakt/Hearth.git
cd Hearth

python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Run the Server Locally
```bash
uvicorn server.simulator_api:app --host 127.0.0.1 --port 8080 --reload
```
Open **`http://127.0.0.1:8080`** in your browser.

### 4. Run with Docker (Easiest for Evaluation)
```bash
# 1. Copy the example configuration (zero external API keys needed out-of-the-box!)
cp .env.example .env

# 2. Launch with Docker Compose
docker compose up --build
```
Open **`http://localhost:8080`** in your browser.

*(Alternatively, standard Docker CLI):*
```bash
docker build -t hearth .
docker run -p 8080:8080 --env-file .env hearth
```

---

## 🧰 MCP Tools Reference

The server exposes standard tools via the Model Context Protocol:

| Tool | Description | Key Inputs |
| :--- | :--- | :--- |
| `get_context` | Returns household calendar events and family preferences. | None |
| `check_conflicts` | Identifies overlapping events on the calendar. | `events` (optional) |
| `get_forecast` | Queries Open-Meteo for temperature, condition, and rain probability. | `location`, `date` |
| `estimate_travel` | Calculates driving time and required departure time with buffer. | `origin_name`, `dest_name`, `target_arrival_time`, `buffer_minutes` |
| `propose_plan` | Assembles weather, travel, checklist, and conflict resolution into a draft plan. | `request` |
| `revise_plan` | Updates items, departure times, or dates on an existing draft plan. | `plan_id`, `instruction` |
| `discard_plan` | Drops an uncommitted draft plan without modifying the calendar. | `plan_id` |
| `reschedule_event` | Creates a draft proposal to move an event to a new date/time. | `event_title`, `target_datetime`, `target_date` |
| `delete_event` | Creates a draft proposal to remove an event from the calendar. | `event_title`, `target_date` |
| `get_event_details`| Returns full details (attendees, notes, location coordinates) for an event. | `event_title` |
| `remember_preference` | Saves a persistent key-value preference to SQLite. | `key`, `value` |

---

## 🧠 Execution Modes

Hearth supports multiple execution modes configured in `.env`:

```ini
# 1. Local Fallback (default, offline, no API key required)
LLM_PROVIDER="fallback"

# 2. AWS Bedrock (Amazon Nova / Claude)
LLM_PROVIDER="bedrock"
AWS_REGION="us-east-1"
AWS_BEDROCK_MODEL="amazon.nova-lite-v1:0"

# 3. Groq Cloud (requires API key)
LLM_PROVIDER="groq"
GROQ_API_KEY="your-api-key"
GROQ_MODEL="llama-3.1-8b-instant"

# 4. Local Ollama
LLM_PROVIDER="ollama"
OLLAMA_BASE_URL="http://127.0.0.1:11434"
OLLAMA_MODEL="llama3.2"
```

The offline router (`fallback`) uses rule-based intent parsing and runs completely locally without external network requests.

---

## 🧪 Testing

Run the test suite with pytest:

```bash
# Run all tests
pytest -v

# Run simulator-specific integration tests
pytest -v tests/test_simulator.py
```

The test suite covers:
* Event creation, rescheduling, and deletion proposals
* Approval gate and token verification
* Undo rollback functionality
* Conflict detection and slot allocation
* Session chat history persistence

---

## 📂 Project Structure

```
Hearth/
├── server/
│   ├── simulator_api.py   # FastAPI routes, approval endpoints, SSE telemetry
│   ├── mcp_server.py      # MCP server definition and tool registration
│   ├── agent.py           # Multi-provider LLM caller and intent router
│   ├── planner.py         # Plan generation, revisions, tokens, and undo ledger
│   ├── tools.py           # Domain logic (travel estimates, weather, conflict checks)
│   ├── db.py              # SQLite access for events, preferences, plans, messages
│   ├── models.py          # Pydantic data schemas
│   ├── config.py          # Environment variable parser
│   ├── seed.py            # Initial scenario seed data
│   └── static/            # Frontend assets (HTML, CSS, vanilla JS)
├── tests/                 # Pytest test suite
├── requirements.txt       # Dependencies
└── .env                   # Configuration file
```

---

## 👤 Maintainer

* **Swastik Bose** ([@VasuBhakt](https://github.com/VasuBhakt))

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).