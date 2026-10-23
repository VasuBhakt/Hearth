"""
Hearth AI Agent Orchestrator: Bridges Model Context Protocol (MCP) tools to LLM engines.
Supports:
1. Local Ollama (e.g. Llama 3.2 3B / Llama 3.1 8B with native function calling)
2. Groq Cloud (ultra-fast Llama 3.3 70B via free API key)
3. AWS Bedrock (Amazon Nova / Claude)
4. Offline Smart Tool Router (Zero-config fallback)
"""
import os
import sys
import time
import json
import asyncio
import httpx
from typing import Optional, Dict, Any, List, Callable

# Ensure local imports resolve
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from config import (
    LLM_PROVIDER,
    GROQ_API_URL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    GROQ_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    DEFAULT_PLAN_STATUS_DRAFT,
    DEFAULT_HOME_NAME,
    DEFAULT_VENUE_NAME,
    DEFAULT_TARGET_DATE,
    DEFAULT_ARRIVAL_DATETIME,
    DEFAULT_DEMO_SCENARIO_PROMPT,
    PACKING_KEYWORD_MATCHES,
    PLAN_CANCEL_KEYWORDS,
    GREETING_KEYWORDS,
    ADD_EVENT_KEYWORDS,
    DELETE_EVENT_KEYWORDS,
    REVISION_KEYWORDS,
    SCHEDULE_KEYWORDS,
    PLANNING_SIGNALS,
    CONFLICT_KEYWORDS,
    WEATHER_KEYWORDS,
)
from db import get_all_events, get_plan
from tools import (
    get_context,
    check_conflicts,
    estimate_travel,
    get_forecast,
    remember_preference,
    add_event,
    remove_event,
    parse_datetime_flexible,
)
from planner import (
    propose_plan,
    revise_plan,
    find_target_event,
    discard_plan,
    propose_event_cancellation,
)

# ============================================================================
# Natural Language Event Extraction Helper
# ============================================================================

def extract_event_details_from_prompt(prompt: str) -> Dict[str, Any]:
    """
    Dynamically extracts title, start_time, end_time, and location from natural language requests.
    Handles phrases like 'add another event please, codeforces contest on 24th october 2026, from 8:05 pm ist'.
    """
    import re
    text = prompt.strip()
    text = re.sub(r'^(please\s+)?(add|create|schedule)\s+(another\s+)?(new\s+)?(event\s+)?(please\s*)?[:,-]?\s*', '', text, flags=re.IGNORECASE)

    title = text
    time_part = ""
    loc_name = None

    on_parts = re.split(r'\s+on\s+', text, maxsplit=1, flags=re.IGNORECASE)
    if len(on_parts) == 2:
        title = on_parts[0].strip()
        time_part = on_parts[1].strip()
    else:
        m = re.search(r'(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
        if m:
            title = text[:m.start()].strip()
            time_part = text[m.start():].strip()

    title = title.strip(" ,.-")
    if not title:
        title = "New Event"
    else:
        title = title.title()

    start_str = time_part if time_part else ""
    end_str = None

    # Check for "from X to Y"
    if time_part:
        to_parts = re.split(r'\s+to\s+', time_part, maxsplit=1, flags=re.IGNORECASE)
        if len(to_parts) == 2 and any(ch.isdigit() for ch in to_parts[1]):
            start_str = to_parts[0].strip()
            end_cand = to_parts[1].strip()
            d_match = re.search(r'(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})', start_str)
            if d_match and not re.search(r'[a-zA-Z]{3,}', end_cand):
                end_str = f"{d_match.group(1)} {end_cand}"
            else:
                end_str = end_cand

    norm_start = parse_datetime_flexible(start_str)
    norm_end = parse_datetime_flexible(end_str) if end_str else None

    return {
        "title": title,
        "start_time": norm_start,
        "end_time": norm_end,
        "location_name": loc_name,
    }

# ============================================================================
# MCP Tool Schemas (OpenAI / Ollama / Bedrock Function Calling Format)
# ============================================================================

MCP_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_context",
            "description": "Retrieve current household schedule events and stored family preferences from SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_conflicts",
            "description": "Detect schedule clashes, overlapping events, or travel buffer violations in the household calendar.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "Retrieve weather forecast (temperature in Celsius, precipitation probability, weather condition) for a venue location and target date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Venue name or address, e.g. City Sports Complex"},
                    "date": {"type": "string", "description": "Target date formatted as YYYY-MM-DD"},
                },
                "required": ["location", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_travel",
            "description": "Calculate driving duration in minutes and recommended departure time from origin to destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting address or Home"},
                    "destination": {"type": "string", "description": "Destination address"},
                    "arrival_time": {"type": "string", "description": "Required arrival time in ISO 8601 format"},
                },
                "required": ["origin", "destination", "arrival_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "Generate an autonomous tournament or weekend coordination plan card. Detects conflicts, checks weather, calculates departure, and prepares packing checklist. Does not mutate calendar until approved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {"type": "string", "description": "User coordination request, e.g. 'Get us ready for Saturday's tournament'"},
                },
                "required": ["request"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revise_plan",
            "description": "Revise an existing draft plan briefing card (e.g. reschedule clashing dentist to Monday, add folding chairs to packing list, shift departure time).",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "ID of the active draft plan to revise"},
                    "instruction": {"type": "string", "description": "Modification instruction, e.g. 'Move the dentist to Monday'"},
                },
                "required": ["plan_id", "instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Add a new calendar event, appointment, or contest to the household schedule. Call this whenever the user asks to add, create, or schedule an event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the event, e.g. 'Codeforces Contest' or 'Dentist Appointment'"},
                    "start_time": {"type": "string", "description": "Start time in ISO format (YYYY-MM-DDTHH:MM:SS), e.g. '2026-10-24T20:05:00'"},
                    "end_time": {"type": "string", "description": "Optional end time in ISO format (YYYY-MM-DDTHH:MM:SS), e.g. '2026-10-24T22:05:00'"},
                    "location_name": {"type": "string", "description": "Optional venue name or 'Online' / 'Home'"},
                    "description": {"type": "string", "description": "Optional details or notes"},
                    "attendees": {"type": "array", "items": {"type": "string"}, "description": "Optional list of family attendees"},
                    "priority": {"type": "integer", "description": "1=Routine, 2=Important, 3=High/Fixed"},
                },
                "required": ["title", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Propose removing, deleting, or cancelling an event or appointment from the household calendar. Generates a draft cancellation card requiring explicit human approval before any calendar modification occurs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_title": {"type": "string", "description": "Title or keyword of the event to cancel/delete, e.g. 'Soccer Tournament' or 'Dentist'"},
                    "event_id": {"type": "string", "description": "Optional specific event ID"},
                    "target_date": {"type": "string", "description": "Optional specific date or day of the event to cancel, e.g. 'October 19th', 'Monday', or '2026-10-19'"},
                },
                "required": ["event_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_plan",
            "description": "Cancel, remove, delete, or discard an active draft coordination plan card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Optional plan ID to cancel"},
                },
            },
        },
    },
]

SYSTEM_PROMPT = """You are Hearth, a self-hosted, privacy-first family assistant MCP agent.
You help a household coordinate family events, youth sports tournaments, appointments, travel, and packing checklists.
You have access to MCP tools: get_context, add_event, delete_event, check_conflicts, get_forecast, estimate_travel, propose_plan, revise_plan, discard_plan, remember_preference.

CRITICAL RULES:
1. ADDING EVENTS: If the user asks to add, create, or schedule a new event or appointment, you MUST call the `add_event` tool with the event details! NEVER call `propose_plan` when the user is asking to add a calendar event.
2. DELETING / REMOVING EVENTS (HUMAN-IN-THE-LOOP): If the user asks to delete, remove, or cancel an event on their calendar (e.g. 'remove the soccer tournament event', 'delete dentist appointment'), you MUST call the `delete_event` tool with the event title or ID! Explain clearly that a draft cancellation proposal has been generated and that their calendar will NOT be modified until they click "Approve" on the card.
3. CANCELLING PLANS: If the user asks to cancel, remove, delete, or clear the draft plan card (e.g. 'cancel plan', 'remove plan', 'start over'), call the `discard_plan` tool!
4. CONFLICT AWARENESS: When get_context, check_conflicts, or add_event returns conflicts (such as Maya's Dentist Appointment directly overlapping with Maya's Soccer Tournament), you MUST prominently alert the user about the clash! Never claim there are no conflicts when a conflict is returned.
5. SCHEDULE INQUIRY: If asked for the schedule, call get_context. Present the events clearly and explicitly warn the user about any clashing events.
6. PLANNING: Only call propose_plan when the user asks to prepare, plan logistics, or get ready for an existing tournament or event.
7. If modifying an existing plan, call revise_plan.
8. GREETINGS & CASUAL CHAT: If greeted (e.g. "hi", "hello"), reply warmly and explain how you can help without calling tools.
9. Be warm, concise, and helpful."""



# ============================================================================
# Tool Dispatcher
# ============================================================================

async def execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    plan_id: Optional[str] = None,
    on_telemetry: Optional[Callable] = None,
) -> tuple[Any, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Executes an MCP tool, calculates latency, broadcasts telemetry,
    and returns (tool_output, optional_plan_card_dict, optional_schedule_dict).
    """
    t0 = time.perf_counter()
    result = None
    plan_card = None
    schedule_data = None

    if tool_name == "get_context":
        result = get_context()
        schedule_data = result
    elif tool_name == "check_conflicts":
        events = get_all_events()
        conflicts = check_conflicts(events)
        result = [c.model_dump() for c in conflicts]
    elif tool_name == "get_forecast":
        loc = tool_args.get("location", DEFAULT_VENUE_NAME)
        dt = tool_args.get("date", DEFAULT_TARGET_DATE)
        fc = await get_forecast(loc, dt)
        result = fc.model_dump()
    elif tool_name == "estimate_travel":
        orig = tool_args.get("origin", DEFAULT_HOME_NAME)
        dest = tool_args.get("destination", DEFAULT_VENUE_NAME)
        arr = tool_args.get("arrival_time", DEFAULT_ARRIVAL_DATETIME)
        buf = tool_args.get("buffer_minutes")
        tr = estimate_travel(
            origin_name=orig,
            dest_name=dest,
            target_arrival_time=arr,
            buffer_minutes=buf,
        )
        result = tr.model_dump()
    elif tool_name == "propose_plan":
        req_str = tool_args.get("request", DEFAULT_DEMO_SCENARIO_PROMPT)
        plan = await propose_plan(req_str)
        plan_card = plan.model_dump()
        result = plan_card
    elif tool_name == "revise_plan":
        target_pid = tool_args.get("plan_id") or plan_id
        instruction = tool_args.get("instruction", "")
        existing = get_plan(target_pid) if target_pid else None
        if existing:
            updated = await revise_plan(target_pid, instruction)
            plan_card = updated.model_dump()
            result = plan_card
        else:
            plan = await propose_plan(instruction or "Resolve schedule conflict")
            plan_card = plan.model_dump()
            result = plan_card
    elif tool_name == "add_event":
        title = tool_args.get("title", "New Event")
        start_time = tool_args.get("start_time", "")
        end_time = tool_args.get("end_time")
        loc_name = tool_args.get("location_name")
        desc = tool_args.get("description")
        attendees = tool_args.get("attendees")
        prio = int(tool_args.get("priority", 1))
        req_items = tool_args.get("required_items")
        result = add_event(
            title=title,
            start_time=start_time,
            end_time=end_time,
            location_name=loc_name,
            description=desc,
            attendees=attendees,
            priority=prio,
            required_items=req_items,
        )
        schedule_data = get_context()
    elif tool_name == "remember_preference":
        key = tool_args.get("key", "")
        val = tool_args.get("value")
        result = remember_preference(key, val)
    elif tool_name == "discard_plan":
        p_id = tool_args.get("plan_id") or plan_id
        result = discard_plan(p_id)
        plan_card = None
    elif tool_name == "delete_event":
        title_cand = tool_args.get("event_title") or tool_args.get("title") or tool_args.get("name")
        eid = tool_args.get("event_id") or tool_args.get("id")
        t_date = tool_args.get("target_date") or tool_args.get("date") or tool_args.get("start_time")
        plan = propose_event_cancellation(event_title=title_cand, event_id=eid, target_date=t_date)
        plan_card = plan.model_dump()
        result = plan_card
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    latency_ms = (time.perf_counter() - t0) * 1000

    if on_telemetry:
        await on_telemetry(tool_name, latency_ms, tool_args, result)

    return result, plan_card, schedule_data


# ============================================================================
# Provider 0: Groq Cloud API (Llama 3.3 70B - Ultra Fast & Precise Function Calling)
# ============================================================================

async def query_groq(
    messages: List[Dict[str, Any]],
    plan_id: Optional[str] = None,
    on_telemetry: Optional[Callable] = None,
    user_query: str = "",
) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Queries Groq Cloud API with native MCP tool calling via async httpx."""
    api_key = (os.environ.get("GROQ_API_KEY") or GROQ_API_KEY).strip().strip('"').strip("'")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    url = os.environ.get("GROQ_API_URL") or GROQ_API_URL
    model = os.environ.get("GROQ_MODEL") or GROQ_MODEL or "openai/gpt-oss-120b"
    payload = {
        "model": model,
        "messages": messages,
        "tools": MCP_TOOL_DEFINITIONS,
        "temperature": GROQ_TEMPERATURE,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hearth/1.0",
    }

    async with httpx.AsyncClient(timeout=GROQ_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()

    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    captured_plan = None
    captured_schedule = None

    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        messages.append(msg)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args or {}

            tool_res, plan, sched = await execute_tool(name, args, plan_id, on_telemetry)
            if plan:
                captured_plan = plan
            if sched:
                captured_schedule = sched

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{int(time.time()*1000)}"),
                "name": name,
                "content": json.dumps(tool_res),
            })

        # Synthesizer hint: tell the LLM what to focus on so it writes a natural summary
        synthesizer_hint = "You are Hearth, a warm family assistant. "
        if user_query:
            synthesizer_hint += f'The user asked: "{user_query}". '
        synthesizer_hint += (
            "Based on the tool results above, write a concise 2-3 sentence response in a friendly, "
            "natural tone. Lead with the most important actionable insight (conflict, departure time, "
            "rain warning, or packing reminder). Never list raw JSON. Be warm, like talking to a family."
        )
        payload_turn2 = {
            "model": model,
            "messages": messages + [{"role": "system", "content": synthesizer_hint}],
            "temperature": GROQ_TEMPERATURE,
        }
        async with httpx.AsyncClient(timeout=GROQ_TIMEOUT_SECONDS) as client:
            resp2 = await client.post(url, headers=headers, json=payload_turn2)
            if resp2.status_code != 200:
                raise RuntimeError(f"HTTP {resp2.status_code} on turn 2: {resp2.text}")
            data2 = resp2.json()

        final_reply = data2.get("choices", [{}])[0].get("message", {}).get("content", "")
        return final_reply, captured_plan, captured_schedule

    return msg.get("content", ""), captured_plan, captured_schedule


# ============================================================================
# Provider 1: Local Ollama
# ============================================================================

async def query_ollama(
    messages: List[Dict[str, Any]],
    plan_id: Optional[str] = None,
    on_telemetry: Optional[Callable] = None,
    user_query: str = "",
) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Queries local Ollama instance with native tool calling via async httpx."""
    base_url = (os.environ.get("OLLAMA_BASE_URL") or OLLAMA_BASE_URL).rstrip("/")
    model = os.environ.get("OLLAMA_MODEL") or OLLAMA_MODEL
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "tools": MCP_TOOL_DEFINITIONS,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hearth/1.0",
    }

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
        data = resp.json()

    msg = data.get("message", {})
    captured_plan = None
    captured_schedule = None

    # Check for tool calls
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        # Append assistant message with tool calls
        messages.append(msg)

        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            tool_res, plan, sched = await execute_tool(name, args, plan_id, on_telemetry)
            if plan:
                captured_plan = plan
            if sched:
                captured_schedule = sched

            # Append tool response
            messages.append({
                "role": "tool",
                "content": json.dumps(tool_res),
            })

        # Second turn: get final natural language synthesis
        synthesizer_hint = "You are Hearth, a warm family assistant. "
        if user_query:
            synthesizer_hint += f'The user asked: "{user_query}". '
        synthesizer_hint += (
            "Based on the tool results above, write a concise 2-3 sentence response in a friendly, "
            "natural tone. Lead with the most important actionable insight. Be warm."
        )
        payload_turn2 = {
            "model": model,
            "messages": messages + [{"role": "system", "content": synthesizer_hint}],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            resp2 = await client.post(url, headers=headers, json=payload_turn2)
            if resp2.status_code != 200:
                raise RuntimeError(f"Ollama turn 2 returned HTTP {resp2.status_code}: {resp2.text}")
            data2 = resp2.json()

        final_reply = data2.get("message", {}).get("content", "")
        return final_reply, captured_plan, captured_schedule

    return msg.get("content", ""), captured_plan, captured_schedule


# ============================================================================
# Provider 2: Smart Local Tool Fallback (Zero-config)
# ============================================================================

async def query_smart_fallback(
    user_msg: str,
    plan_id: Optional[str] = None,
    on_telemetry: Optional[Callable] = None,
) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Deterministically routes user requests to real MCP tools when no external LLM is reachable.
    """
    lower = user_msg.lower().strip()
    captured_plan = None
    captured_schedule = None

    # 1. Greetings & Casual Chat
    is_greeting = any(lower == k or lower.startswith(f"{k} ") for k in GREETING_KEYWORDS)
    if is_greeting:
        return (
            "Hello! I'm **Hearth**, your privacy-first family assistant coordinator. "
            "I can help you coordinate family schedules, add new events, check for calendar conflicts "
            "(such as Maya's dentist appointment overlapping with her soccer tournament), "
            "monitor weather forecasts, and generate tournament readiness plans with packing checklists.\n\n"
            "Try asking: *\"What's on our schedule?\"* or *\"Get us ready for Saturday's tournament\"*."
        ), None, None

    # 2. Delete / Remove Calendar Event Intent (Human-in-the-Loop)
    is_delete_event = (
        any(k in lower for k in DELETE_EVENT_KEYWORDS)
        or (any(w in lower for w in ["remove", "delete", "cancel"]) and any(w in lower for w in ["event", "appointment", "match", "tournament", "game", "lesson", "practice", "dentist", "soccer", "groceries"]))
    )
    if is_delete_event:
        import re
        # Detect any explicit dates or weekdays mentioned
        date_match = re.search(
            r'\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?\s+of\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2}|\b\d{1,2}(?:st|nd|rd|th)\b)\b',
            user_msg,
            flags=re.IGNORECASE,
        )
        target_date_str = date_match.group(0) if date_match else None

        target_title = re.sub(r'^(please\s+)?(i\s+asked\s+you\s+to\s+)?(remove|delete|cancel|drop)\s+(the\s+)?', '', user_msg, flags=re.IGNORECASE)
        target_title = re.sub(r'\s+event\b.*', '', target_title, flags=re.IGNORECASE).strip(" '\"")
        _, plan, _ = await execute_tool("delete_event", {"event_title": target_title, "target_date": target_date_str}, plan_id, on_telemetry)
        ev_title = plan.get("title", f"Cancel: {target_title}").replace("Cancel: ", "") if plan else target_title
        return (
            f"I've prepared a cancellation card to remove **{ev_title}** from your calendar. "
            f"To keep you in control, your calendar has not been modified yet. "
            f"Please review the cancellation card below and click **Approve Plan** to confirm, or **Dismiss** to keep the event."
        ), plan, None

    # 3. Plan Cancellation / Removal Intent
    is_cancel_plan = any(k in lower for k in PLAN_CANCEL_KEYWORDS) or any(lower == k for k in ["cancel", "discard", "delete", "clear", "remove"])
    if is_cancel_plan:
        res, _, _ = await execute_tool("discard_plan", {"plan_id": plan_id}, plan_id, on_telemetry)
        return "🗑️ I've cancelled and cleared your draft plan. Your calendar and schedule remain unchanged.", None, None

    # 3. Add Event Intent
    is_add_event = (
        any(k in lower for k in ADD_EVENT_KEYWORDS)
        or (lower.startswith("add ") and not any(k in lower for k in ["chair", "snack", "towel", "water", "umbrella", "item", "pack", "gear"]))
    )
    if is_add_event:
        details = extract_event_details_from_prompt(user_msg)
        res, _, sched = await execute_tool("add_event", details, plan_id, on_telemetry)
        ev = res.get("event", {}) if isinstance(res, dict) else {}
        title = ev.get("title", details.get("title", "New Event"))
        try:
            dt_s = datetime.fromisoformat(ev.get("start_time", ""))
            date_s = dt_s.strftime("%a, %b %d, %Y")
            time_s = dt_s.strftime("%I:%M %p")
            if ev.get("end_time"):
                dt_e = datetime.fromisoformat(ev.get("end_time", ""))
                time_s += f" – {dt_e.strftime('%I:%M %p')}"
            time_display = f"📅 {date_s} ⏰ {time_s}"
        except Exception:
            start_str = ev.get("start_time", "")[:16].replace("T", " ")
            end_str = ev.get("end_time", "")[11:16]
            time_display = f"{start_str} – {end_str}" if end_str else start_str
        clashes = res.get("conflicts", []) if isinstance(res, dict) else []

        lines = [f"✅ Added **{title}** to your calendar ({time_display})."]
        if clashes:
            lines.append(f"\n⚠️ **Warning: Schedule Conflict Detected**\n{clashes[0].get('details', '')}")
            lines.append("Would you like me to reschedule the conflicting event for you?")
        else:
            lines.append("\nAll clear! No overlapping conflicts detected with this event.")

        return "\n".join(lines), None, sched

    # 3. Check for revision of active draft plan (strictly packing or rescheduling, never adding events)
    is_revision = False
    if plan_id and not is_add_event:
        existing = get_plan(plan_id)
        if existing and existing.status == DEFAULT_PLAN_STATUS_DRAFT:
            if any(k in lower for k in REVISION_KEYWORDS):
                is_revision = True

    if is_revision and plan_id:
        res, plan, sched = await execute_tool("revise_plan", {"plan_id": plan_id, "instruction": user_msg}, plan_id, on_telemetry)
        return "I've updated your plan card. Let me know when you'd like to approve it!", plan, sched

    # 4. Schedule / Calendar question
    is_schedule = any(k in lower for k in SCHEDULE_KEYWORDS)
    is_planning = any(k in lower for k in PLANNING_SIGNALS)

    if is_schedule and not is_planning:
        ctx, _, sched = await execute_tool("get_context", {}, plan_id, on_telemetry)
        conflicts, _, _ = await execute_tool("check_conflicts", {}, plan_id, on_telemetry)
        events = ctx.get("events", []) if isinstance(ctx, dict) else []

        if not events:
            return "Your calendar is currently clear. There are no scheduled events.", None, sched

        lines = ["Here is your current household schedule:\n"]
        for ev in events:
            try:
                dt_start = datetime.fromisoformat(ev["start_time"])
                dt_end = datetime.fromisoformat(ev["end_time"])
                date_str = dt_start.strftime("%a, %b %d, %Y")
                time_str = f"{dt_start.strftime('%I:%M %p')} – {dt_end.strftime('%I:%M %p')}"
                datetime_display = f"📅 {date_str} ⏰ {time_str}"
            except Exception:
                start_dt = ev["start_time"][:16].replace("T", " ")
                end_dt = ev["end_time"][11:16]
                datetime_display = f"{start_dt} – {end_dt}"

            loc_name = ev.get("location_name") or (ev.get("location", {}).get("name") if isinstance(ev.get("location"), dict) else None)
            loc = f" at {loc_name}" if loc_name else ""
            lines.append(f"• **{ev['title']}**: {datetime_display}{loc}")

        if conflicts:
            lines.append(f"\n⚠️ **Heads up**: I detected {len(conflicts)} conflict(s) (e.g. {conflicts[0]['details']}).")
            lines.append("Would you like me to resolve this conflict and prepare a coordination plan for you?")
        else:
            lines.append("\n✅ All clear! No overlapping conflicts detected.")

        return "\n".join(lines), None, sched

    # 5. Conflict question
    if any(k in lower for k in CONFLICT_KEYWORDS) and not is_planning:
        conflicts, _, _ = await execute_tool("check_conflicts", {}, plan_id, on_telemetry)
        if conflicts:
            c_details = "\n".join(f"• {c['details']}" for c in conflicts)
            return f"I detected {len(conflicts)} conflict(s) on your calendar:\n{c_details}\n\nWould you like me to reschedule the conflicting event?", None, None
        return "No conflicts found on your calendar!", None, None

    # 6. Weather question
    if any(k in lower for k in WEATHER_KEYWORDS) and not is_planning:
        fc, _, _ = await execute_tool("get_forecast", {"location": DEFAULT_VENUE_NAME, "date": DEFAULT_TARGET_DATE}, plan_id, on_telemetry)
        rain_info = f"Rain alert: {fc['precipitation_chance_percent']}% chance of rain." if fc.get("rain_warning") else "No rain expected."
        return f"The forecast for {fc['location_name']} on {fc['date']} is {fc['temperature_c']}°C with {fc['weather_condition']}. {rain_info}", None, None

    # 7. Planning / Coordination Request
    events = get_all_events()
    matched_event = find_target_event(user_msg, events)

    if is_planning or matched_event:
        _, _, _ = await execute_tool("get_context", {}, plan_id, on_telemetry)
        _, _, _ = await execute_tool("check_conflicts", {}, plan_id, on_telemetry)
        plan_res, plan, _ = await execute_tool("propose_plan", {"request": user_msg}, plan_id, on_telemetry)

        conf_count = len(plan.get("conflicts", [])) if plan else 0
        text = (
            f"I put together a preview for {plan.get('title', 'Your Plan')}. "
            f"I found {conf_count} conflict(s), checked the weather forecast, and estimated your departure time. "
            f"Review the plan card below—nothing is saved until you approve it!"
        )
        return text, plan, None

    # 8. Unmatched Request Fallback (Zero Hallucination)
    return (
        "I couldn't find a matching event on your calendar for that request. "
        "You can ask me to **view your schedule**, **add a new event**, or **prepare for Saturday's tournament**."
    ), None, None


# ============================================================================
# Main Agent Entry Point
# ============================================================================

async def chat_with_agent(
    user_message: str,
    plan_id: Optional[str] = None,
    on_telemetry: Optional[Callable] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Dispatches user conversation through the configured LLM provider,
    executing MCP tools dynamically and returning structured response.
    Conversation history (list of {role, content} dicts) is threaded into
    the LLM context window for multi-turn awareness.
    """
    history = conversation_history or []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    provider = os.environ.get("LLM_PROVIDER", LLM_PROVIDER).lower().strip()
    active_groq_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY

    # 1. Groq Cloud Engine (Llama 3.3 70B - Preferred Primary)
    if provider == "groq" or (active_groq_key and provider not in ["ollama", "fallback"]):
        try:
            reply, plan, sched = await query_groq(messages, plan_id, on_telemetry, user_query=user_message)
            if reply and reply.strip():
                return {"reply": reply, "message": reply, "plan": plan, "schedule": sched}
        except Exception as e:
            print(f"[Agent] Groq query notice ({e}), falling back to smart router.")

    # 2. Local Ollama (Only if explicitly selected)
    if provider == "ollama":
        try:
            reply, plan, sched = await query_ollama(messages, plan_id, on_telemetry, user_query=user_message)
            if reply and reply.strip():
                # If user asked to add an event, verify it was recorded into database
                lower = user_message.lower()
                is_add = (
                    any(k in lower for k in ADD_EVENT_KEYWORDS)
                    or (lower.startswith("add ") and not any(k in lower for k in PACKING_KEYWORD_MATCHES))
                )
                if is_add and not sched:
                    details = extract_event_details_from_prompt(user_message)
                    tool_res, _, sched = await execute_tool("add_event", details, plan_id, on_telemetry)
                return {"reply": reply, "message": reply, "plan": plan, "schedule": sched}
        except Exception as e:
            print(f"[Agent] Ollama query failed ({e}), falling back to smart tool router.")

    # 3. Smart local router fallback (Offline / Zero-config)
    reply, plan, sched = await query_smart_fallback(user_message, plan_id, on_telemetry)
    return {"reply": reply, "message": reply, "plan": plan, "schedule": sched}
