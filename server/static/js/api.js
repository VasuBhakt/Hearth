/**
 * Hearth API Client: Handles REST requests and Server-Sent Events (SSE) telemetry.
 * All paths and endpoints are dynamic and relative.
 */

// Stable session ID for this browser tab — persists across messages so the server
// can maintain a rolling conversation history window for multi-turn awareness.
const _sessionId = (() => {
  const key = 'hearth_session_id';
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
})();

export const api = {
  /**
   * Fetches dynamic server and runtime configuration.
   */
  async fetchConfig() {
    const res = await fetch('/api/config');
    if (!res.ok) throw new Error('Failed to load server configuration.');
    return await res.json();
  },

  /**
   * Sends a typed or voice user message to the Hearth planner orchestrator.
   * session_id enables multi-turn conversation history on the server.
   */
  async sendChatMessage(message, planId = null) {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, plan_id: planId, session_id: _sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to process chat message.');
    }
    return await res.json();
  },


  /**
   * Human Approval Gate: Mints approval token and commits the plan.
   */
  async approvePlan(planId) {
    const res = await fetch('/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Approval failed.');
    }
    return await res.json();
  },

  /**
   * Surgical Rollback: Restores previous state using the undo ledger.
   */
  async undoPlan(planId = null) {
    const res = await fetch('/api/undo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Undo operation failed.');
    }
    return await res.json();
  },

  /**
   * Resets SQLite demo scenario.
   */
  async resetDatabase() {
    const res = await fetch('/api/reset', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to reset database.');
    return await res.json();
  },

  /**
   * Subscribes to the real-time Server-Sent Events (SSE) telemetry feed.
   */
  connectTelemetryStream(onEvent, onError) {
    const evtSource = new EventSource('/api/stream');
    evtSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (onEvent) onEvent(payload);
      } catch (e) {
        console.error('SSE JSON parsing error:', e);
      }
    };
    evtSource.onerror = (err) => {
      if (onError) onError(err);
    };
    return evtSource;
  },
};
