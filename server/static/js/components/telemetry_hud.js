/**
 * Telemetry HUD Component: Real-time inspector for Streamable HTTP MCP tool calls.
 * Displays live tool calls, latencies, HTTP/MCP statuses, and expandable JSON payloads.
 */
import { stateStore } from '../state.js';

export function initTelemetryHud(elements) {
  const { feedEl, countPillEl, btnClearEl } = elements;
  if (!feedEl) return;

  // Track expanded item IDs so toggling doesn't reset on new messages
  const expandedItems = new Set();

  stateStore.subscribe((state) => {
    const logs = state.telemetryLogs || [];

    // Update event counter pill
    if (countPillEl) {
      countPillEl.textContent = `${logs.length} ${logs.length === 1 ? 'call' : 'calls'}`;
    }

    // Render feed
    if (logs.length === 0) {
      feedEl.innerHTML = `
        <div class="telemetry-empty-state">
          <div class="telemetry-empty-icon">📡</div>
          <div>Listening for Streamable HTTP tool calls...</div>
          <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 4px;">
            Trigger a scenario or speak a command to inspect live MCP traffic.
          </div>
        </div>
      `;
      return;
    }

    feedEl.innerHTML = logs.map((entry, idx) => {
      const itemId = `telem_${idx}`;
      const isExpanded = expandedItems.has(itemId);
      const latencyStr = entry.latency_ms != null ? `${entry.latency_ms} ms` : '< 5ms';
      const statusStr = entry.status || 'OK';
      const timeStr = entry.timestamp ? entry.timestamp.substring(11, 19) : new Date().toLocaleTimeString();
      const toolName = entry.tool || 'mcp.unknown';

      // Pretty syntax-highlighted payload
      const payloadObj = {
        tool: toolName,
        args: entry.args || {},
        result: entry.result || {}
      };
      const formattedJson = syntaxHighlightJson(payloadObj);

      return `
        <div class="telemetry-item" id="${itemId}">
          <div class="telemetry-item-header">
            <span class="tool-name-tag">${escapeHtml(toolName)}</span>
            <div class="telemetry-metrics-row">
              <span class="badge-latency">${escapeHtml(latencyStr)}</span>
              <span class="badge-status">${escapeHtml(statusStr)}</span>
              <span class="telemetry-timestamp">${escapeHtml(timeStr)}</span>
            </div>
          </div>
          
          <button class="telemetry-payload-toggle" data-target="${itemId}">
            <span class="toggle-icon">${isExpanded ? '▼' : '▶'}</span>
            <span>${isExpanded ? 'Hide Payload' : 'View Payload & Result'}</span>
          </button>
          
          <div class="json-viewer-box" style="display: ${isExpanded ? 'block' : 'none'};">
            ${formattedJson}
          </div>
        </div>
      `;
    }).join('');

    // Attach click events for collapsible JSON viewer
    feedEl.querySelectorAll('.telemetry-payload-toggle').forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const targetId = btn.getAttribute('data-target');
        const box = feedEl.querySelector(`#${targetId} .json-viewer-box`);
        const icon = btn.querySelector('.toggle-icon');
        const label = btn.querySelector('span:nth-child(2)');

        if (expandedItems.has(targetId)) {
          expandedItems.delete(targetId);
          if (box) box.style.display = 'none';
          if (icon) icon.textContent = '▶';
          if (label) label.textContent = 'View Payload & Result';
        } else {
          expandedItems.add(targetId);
          if (box) box.style.display = 'block';
          if (icon) icon.textContent = '▼';
          if (label) label.textContent = 'Hide Payload';
        }
      };
    });
  });

  // Clear button handler
  if (btnClearEl) {
    btnClearEl.addEventListener('click', () => {
      expandedItems.clear();
      stateStore.clearTelemetry();
    });
  }
}

/**
 * Syntax highlights JSON string into styled HTML spans.
 */
function syntaxHighlightJson(jsonObj) {
  let json = JSON.stringify(jsonObj, null, 2);
  json = escapeHtml(json);
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      let cls = 'json-number';
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = 'json-key';
        } else {
          cls = 'json-string';
        }
      } else if (/true|false/.test(match)) {
        cls = 'json-boolean';
      } else if (/null/.test(match)) {
        cls = 'json-null';
      }
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
