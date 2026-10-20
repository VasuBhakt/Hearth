/**
 * Plan Card Component: Renders interactive, high-end glassmorphic briefing cards
 * with live Approve, Quick Edit, and Surgical Undo handlers.
 */
import { api } from '../api.js';
import { stateStore } from '../state.js';

export function renderPlanCardHtml(plan) {
  if (!plan) return '';

  const isCommitted = plan.status === 'committed';
  const statusClass = isCommitted ? 'committed' : 'draft';
  const statusLabel = isCommitted ? 'Committed & Synced' : 'Draft Preview';

  // Conflict Alert
  let conflictHtml = '';
  if (plan.conflicts && plan.conflicts.length > 0) {
    const c = plan.conflicts[0];
    conflictHtml = `
      <div class="conflict-alert-box">
        <span class="conflict-icon">⚠️</span>
        <div class="conflict-content">
          <div class="conflict-title">Schedule Conflict: ${escapeHtml(c.conflict_type)}</div>
          <div class="conflict-desc">${escapeHtml(c.details)}</div>
        </div>
      </div>
    `;
  }

  // Weather Tile
  let weatherHtml = '<div class="metric-value">Mild</div>';
  if (plan.weather) {
    const temp = plan.weather.temperature_c != null ? `${plan.weather.temperature_c}°C` : '--';
    const cond = plan.weather.weather_condition || 'Clear';
    const rain = plan.weather.rain_warning ? '🌧️ Rain Alert' : '☀️ Outdoor Good';
    weatherHtml = `
      <div class="metric-value">${temp} · ${escapeHtml(cond)}</div>
      <div class="metric-detail">${rain} (${plan.weather.precipitation_chance_percent || 0}%)</div>
    `;
  }

  // Departure Tile
  let leaveTimeStr = plan.leave_by ? plan.leave_by.substring(11, 16) : '--:--';
  const targetDateStr = plan.target_date || 'Target Event';

  // Packing Checklist
  let packingChipsHtml = '';
  if (plan.packing_list && plan.packing_list.length > 0) {
    packingChipsHtml = plan.packing_list
      .map(
        (item, idx) => `
        <label class="checklist-chip" id="pack_item_${idx}">
          <input type="checkbox" checked />
          <span>${escapeHtml(item)}</span>
        </label>
      `
      )
      .join('');
  } else {
    packingChipsHtml = '<span class="metric-detail">No items specified.</span>';
  }

  // Proposed Changes Bullets
  let changesHtml = '';
  if (plan.proposed_changes && plan.proposed_changes.length > 0) {
    changesHtml = `
      <div class="proposed-changes-box">
        <div class="section-label">Recommended Strategy</div>
        ${plan.proposed_changes
          .map(
            (ch) => `
          <div class="change-item">
            <span class="change-bullet">›</span>
            <span>${escapeHtml(ch)}</span>
          </div>
        `
          )
          .join('')}
      </div>
    `;
  }

  // Action Buttons Bar
  let actionsBarHtml = '';
  if (!isCommitted) {
    actionsBarHtml = `
      <div class="card-actions-bar">
        <div class="primary-actions-row">
          <button class="btn-approve" id="btn-approve-${plan.id}" data-plan-id="${plan.id}">
            <span>✓</span> Approve & Commit Plan
          </button>
        </div>
        <div class="quick-edits-row">
          <span class="quick-edit-label">Quick Adjust:</span>
          <button class="btn-quick-edit" data-edit="Move the dentist to Monday">Move dentist to Monday</button>
          <button class="btn-quick-edit" data-edit="Leave 15 minutes earlier">Leave 15m earlier</button>
          <button class="btn-quick-edit" data-edit="Add folding chairs to packing list">+ Folding chairs</button>
        </div>
      </div>
    `;
  } else {
    actionsBarHtml = `
      <div class="card-actions-bar">
        <div class="primary-actions-row">
          <button class="btn-undo" id="btn-undo-${plan.id}" data-plan-id="${plan.id}">
            <span>⎌</span> Undo Plan (Surgical Rollback)
          </button>
        </div>
      </div>
    `;
  }

  return `
    <div class="plan-card-widget ${statusClass}" id="card-${plan.id}">
      <div class="card-header">
        <div class="card-title-group">
          <div class="card-title">${escapeHtml(plan.title)}</div>
          <div class="card-date-sub">Scheduled Date: ${escapeHtml(targetDateStr)}</div>
        </div>
        <span class="card-status-badge ${statusClass}">${statusLabel}</span>
      </div>

      ${conflictHtml}

      <div class="plan-metrics-grid">
        <div class="metric-tile">
          <div class="metric-label">🚗 Recommended Departure</div>
          <div class="metric-value">Leave by ${leaveTimeStr}</div>
          <div class="metric-detail">Calculated with travel & buffer window</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">🌤️ Venue Forecast</div>
          ${weatherHtml}
        </div>
      </div>

      <div class="packing-section">
        <div class="section-label">Prepared Checklist & Supplies</div>
        <div class="packing-checklist">
          ${packingChipsHtml}
        </div>
      </div>

      ${changesHtml}

      ${actionsBarHtml}
    </div>
  `;
}

/**
 * Attaches event listeners to interactive Plan Card buttons (Approve, Undo, Quick Edit).
 */
export function bindPlanCardEvents(container, onQuickEdit) {
  if (!container) return;

  // Approve button handler
  container.querySelectorAll('.btn-approve').forEach((btn) => {
    btn.onclick = async () => {
      const planId = btn.getAttribute('data-plan-id');
      try {
        btn.textContent = '⏳ Verifying Approval Token...';
        btn.disabled = true;

        const res = await api.approvePlan(planId);
        stateStore.setActivePlan(res.plan);
        stateStore.addMessage(
          'assistant',
          `✅ Plan approved! Token verified and burned. Calendar updated with ${res.commit.actions_executed} change(s). An undo snapshot is available.`
        );
      } catch (err) {
        alert('Commit rejected: ' + err.message);
        btn.disabled = false;
        btn.textContent = '✓ Approve & Commit Plan';
      }
    };
  });

  // Undo button handler
  container.querySelectorAll('.btn-undo').forEach((btn) => {
    btn.onclick = async () => {
      const planId = btn.getAttribute('data-plan-id');
      try {
        btn.textContent = '⏳ Executing Surgical Rollback...';
        btn.disabled = true;

        const res = await api.undoPlan(planId);
        stateStore.setActivePlan(res.plan);
        stateStore.addMessage(
          'assistant',
          `⎌ Rollback complete! Restored ${res.undo.restored_events_count} event(s) to exact pre-commit state. Plan reset to draft.`
        );
      } catch (err) {
        alert('Undo failed: ' + err.message);
        btn.disabled = false;
        btn.textContent = '⎌ Undo Plan (Surgical Rollback)';
      }
    };
  });

  // Quick Edit buttons handler
  container.querySelectorAll('.btn-quick-edit').forEach((btn) => {
    btn.onclick = () => {
      const instruction = btn.getAttribute('data-edit');
      if (onQuickEdit) {
        onQuickEdit(instruction);
      }
    };
  });
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
