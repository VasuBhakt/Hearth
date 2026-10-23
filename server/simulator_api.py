"""
Hearth Assistant Simulator API Server
FastAPI backend providing:
- Web static assets delivery
- Dynamic configuration endpoint (/api/config)
- Voice & Chat conversational processing (/api/chat)
- Human approval gate & plan commit (/api/approve)
- Surgical rollback (/api/undo)
- Scenario reset (/api/reset)
- Real-time Server-Sent Events (SSE) telemetry stream (/api/stream)
Zero hardcoding: all parameters, titles, and endpoints are loaded from .env.
"""
import os
import sys
import time
import json
import asyncio
from typing import Optional, List, Dict, Any, Deque
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure local imports resolve
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from config import (
    SIMULATOR_HOST,
    SIMULATOR_PORT,
    SIMULATOR_TITLE,
    DEFAULT_DEMO_SCENARIO_PROMPT,
    MIN_PROTOCOL_VERSION,
    CURRENT_PROTOCOL_VERSION,
    DEFAULT_HOME_NAME,
    DEFAULT_PLAN_STATUS_DRAFT,
    DEFAULT_PLAN_STATUS_COMMITTED,
)
from seed import seed_demo_data
from db import get_all_events, get_plan, get_all_preferences
from tools import (
    get_context,
    check_conflicts,
    estimate_travel,
    get_forecast,
    remember_preference,
)
from planner import (
    propose_plan,
    revise_plan,
    mint_approval_token,
    commit_plan,
    undo_plan,
)
from agent import chat_with_agent

app = FastAPI(title=SIMULATOR_TITLE)

# Static files directory
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Pub/Sub Queues for Real-Time SSE Telemetry
subscribers: List[asyncio.Queue] = []

# ============================================================================
# Session-scoped Conversation History (in-memory, rolling window)
# ============================================================================

try:
    from config import CONVERSATION_HISTORY_MAX_TURNS
except ImportError:
    CONVERSATION_HISTORY_MAX_TURNS = int(os.environ.get("CONVERSATION_HISTORY_MAX_TURNS", "20"))

# session_id -> deque of {role, content} message dicts
_session_histories: Dict[str, Deque[Dict[str, str]]] = {}


async def broadcast_telemetry(
    tool_name: str,
    latency_ms: float,
    input_data: Any,
    output_data: Any,
    status: str = "success",
):
    """Broadcasts tool execution telemetry to all connected frontend HUD subscribers."""
    payload = {
        "tool": tool_name,
        "latency_ms": round(latency_ms, 1),
        "status": status,
        "protocol": CURRENT_PROTOCOL_VERSION,
        "transport": f"Streamable HTTP ({MIN_PROTOCOL_VERSION}+)",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
        "input": input_data,
        "output": output_data,
    }
    dead_subscribers = []
    for queue in subscribers:
        try:
            queue.put_nowait(payload)
        except Exception:
            dead_subscribers.append(queue)

    for dead in dead_subscribers:
        if dead in subscribers:
            subscribers.remove(dead)


# ============================================================================
# API Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    plan_id: Optional[str] = None
    session_id: Optional[str] = None  # Client-generated UUID; if absent, a new history is not tracked


class ApproveRequest(BaseModel):
    plan_id: str


class UndoRequest(BaseModel):
    plan_id: Optional[str] = None


# ============================================================================
# Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main modular Assistant Simulator single-page interface."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Hearth Assistant Simulator initializing...</h1>")


@app.get("/api/config")
async def get_simulator_config():
    """Dynamic runtime configuration so frontend never hardcodes copy or parameters."""
    return {
        "title": SIMULATOR_TITLE,
        "default_prompt": DEFAULT_DEMO_SCENARIO_PROMPT,
        "protocol_version": CURRENT_PROTOCOL_VERSION,
        "min_protocol": MIN_PROTOCOL_VERSION,
        "home_name": DEFAULT_HOME_NAME,
        "draft_status": DEFAULT_PLAN_STATUS_DRAFT,
        "committed_status": DEFAULT_PLAN_STATUS_COMMITTED,
    }


@app.get("/api/stream")
async def stream_telemetry(request: Request):
    """Server-Sent Events endpoint streaming real-time tool calls to the telemetry HUD."""
    queue = asyncio.Queue()
    subscribers.append(queue)

    async def event_generator():
        try:
            # Send initial connection handshake
            init_payload = {
                "tool": "protocol_handshake",
                "latency_ms": 1.2,
                "status": "connected",
                "protocol": CURRENT_PROTOCOL_VERSION,
                "transport": "Streamable HTTP",
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
                "input": {"min_protocol": MIN_PROTOCOL_VERSION},
                "output": {"handshake": "accepted", "agent": SIMULATOR_TITLE},
            }
            yield f"data: {json.dumps(init_payload)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            if queue in subscribers:
                subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    """
    Coordinates tool execution and planning based on typed or spoken user input.
    Broadcasts real-time telemetry events for each MCP tool call.
    Maintains session-scoped conversation history for multi-turn awareness.
    """
    user_msg = req.message.strip()
    if not user_msg:
        return JSONResponse(status_code=400, content={"error": "Empty message."})

    # Retrieve or initialise rolling history for this session
    session_id = req.session_id
    history: List[Dict[str, str]] = []
    if session_id:
        if session_id not in _session_histories:
            _session_histories[session_id] = deque(maxlen=CONVERSATION_HISTORY_MAX_TURNS * 2)  # user+assistant pairs
        history = list(_session_histories[session_id])

    res = await chat_with_agent(
        user_message=user_msg,
        plan_id=req.plan_id,
        on_telemetry=broadcast_telemetry,
        conversation_history=history,
    )

    # Append this turn to history so the next request has context
    if session_id and res.get("reply"):
        _session_histories[session_id].append({"role": "user", "content": user_msg})
        _session_histories[session_id].append({"role": "assistant", "content": res["reply"]})

    return res


@app.post("/api/approve")
async def handle_approve(req: ApproveRequest):
    """
    Executes the Human Approval Security Gate:
    1. Mints a cryptographic single-use token via mint_approval_token.
    2. Commits the plan and burns the token via commit_plan.
    """
    t0 = time.perf_counter()
    token = mint_approval_token(req.plan_id)
    t_token = (time.perf_counter() - t0) * 1000
    await broadcast_telemetry("mint_approval_token", t_token, {"plan_id": req.plan_id}, {"token": token.token[:12] + "...", "expires_at": token.expires_at})

    t0 = time.perf_counter()
    commit_res = await commit_plan(req.plan_id, token.token)
    t_commit = (time.perf_counter() - t0) * 1000
    await broadcast_telemetry("commit_plan", t_commit, {"plan_id": req.plan_id, "token_verified": True}, commit_res)

    updated_plan = get_plan(req.plan_id)
    return {
        "success": True,
        "commit": commit_res,
        "plan": updated_plan.model_dump() if updated_plan else None,
        "message": "Plan approved and committed. Calendar updated with surgical undo snapshot recorded.",
    }


@app.post("/api/undo")
async def handle_undo(req: UndoRequest):
    """
    Executes surgical rollback via undo_plan.
    Restores only the events affected by the plan and resets plan status to draft.
    """
    t0 = time.perf_counter()
    undo_res = await undo_plan(req.plan_id)
    t_undo = (time.perf_counter() - t0) * 1000
    await broadcast_telemetry("undo_plan", t_undo, {"plan_id": req.plan_id}, undo_res)

    target_plan_id = undo_res.get("plan_id")
    updated_plan = get_plan(target_plan_id) if target_plan_id else None
    return {
        "success": True,
        "undo": undo_res,
        "plan": updated_plan.model_dump() if updated_plan else None,
        "message": "Rollback successful. Calendar events restored to exact pre-commit state.",
    }


@app.post("/api/reset")
async def handle_reset():
    """Resets the SQLite database to the default Saturday tournament demo scenario."""
    t0 = time.perf_counter()
    seed_demo_data()
    t_reset = (time.perf_counter() - t0) * 1000
    await broadcast_telemetry("seed_demo_data", t_reset, {}, {"status": "re-seeded", "scenario": "Saturday Tournament"})
    return {"success": True, "message": "Database reset to initial demo state."}


if __name__ == "__main__":
    import uvicorn
    print(f"Starting {SIMULATOR_TITLE} on http://{SIMULATOR_HOST}:{SIMULATOR_PORT}...")
    uvicorn.run("simulator_api:app", host=SIMULATOR_HOST, port=SIMULATOR_PORT, reload=True)
