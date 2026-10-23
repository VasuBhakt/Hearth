/**
 * Plan Card Component: Renders interactive, high-end glassmorphic briefing cards
 * with live Approve, Quick Edit, and Surgical Undo handlers.
 */
import { api } from '../api.js';
import { stateStore } from '../state.js';
import { formatEventDateTime, formatDate, formatTime } from '../datetime.js';

export function renderPlanCardHtml(plan) {
  if (!plan) return '';

  if (plan.status === 'cancelled') {
    return `
      <div class="plan-card-widget cancelled" style="opacity: 0.55; border: 1px dashed rgba(255, 255, 255, 0.2); padding: 16px 20px;">
        <div class="card-header" style="margin-bottom: 0; padding-bottom: 0; border-bottom: none;">
          <div class="card-title-group">
            <div class="card-title" style="text-decoration: line-through; color: var(--text-dim); font-size: 1rem;">${escapeHtml(plan.title)}</div>
            <div class="card-date-sub" style="margin-top: 2px;">Plan cancelled & removed</div>
          </div>
          <span class="card-status-badge draft" style="background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25);">Cancelled</span>
        </div>
      </div>
    `;
  }

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

  const isCancellation = Boolean(
    (plan.title && plan.title.startsWith('Cancel:')) ||
    (plan.action_items && plan.action_items.some((a) => a.action === 'delete_event'))
  );

  // Departure and Date Formatting
  const formattedLeaveTime = formatTime(plan.leave_by);
  const formattedTargetDate = plan.target_date
    ? formatDate(plan.target_date, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
    : 'Target Event';

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

  // Rescheduled Event Timing Badges (if any action items reschedule events)
  let rescheduledEventsHtml = '';
  const rescheduleActions = (plan.action_items || []).filter(
    (a) => a.action === 'reschedule_event' || (a.new_start_time && a.event_title)
  );
  if (rescheduleActions.length > 0) {
    rescheduledEventsHtml = `
      <div class="plan-rescheduled-events">
        <div class="section-label">Rescheduled Event Timing</div>
        <div class="rescheduled-list">
          ${rescheduleActions
            .map((item) => {
              const dtInfo = formatEventDateTime(item.new_start_time, item.new_end_time);
              return `
              <div class="rescheduled-item">
                <span class="rescheduled-title">🔄 ${escapeHtml(item.event_title || 'Event')}</span>
                <div class="schedule-event-datetime">
                  <span class="schedule-event-date" title="Rescheduled Date">📅 ${escapeHtml(dtInfo.dateStr)}</span>
                  <span class="schedule-event-time" title="Rescheduled Time Window">⏰ ${escapeHtml(dtInfo.timeStr)}</span>
                </div>
              </div>
            `;
            })
            .join('')}
        </div>
      </div>
    `;
  }

  // Proposed Changes Bullets
  let changesHtml = '';
  if (plan.proposed_changes && plan.proposed_changes.length > 0) {
    changesHtml = `
      <div class="proposed-changes-box">
        <div class="section-label">${isCancellation ? 'Cancellation Details' : 'Recommended Strategy'}</div>
        ${plan.proposed_changes
          .map(
            (ch) => `
          <div class="change-item">
            <span class="change-bullet" style="${isCancellation ? 'color: #ef4444;' : ''}">›</span>
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
          <button class="btn-approve" id="btn-approve-${plan.id}" data-plan-id="${plan.id}" style="${isCancellation ? 'background: linear-gradient(135deg, #ef4444, #dc2626);' : ''}">
            <span>${isCancellation ? '🗑️' : '✓'}</span> ${isCancellation ? 'Confirm & Remove Event' : 'Approve & Commit Plan'}
          </button>
        </div>
        ${
          !isCancellation
            ? `
        <div class="quick-edits-row">
          <span class="quick-edit-label">Quick Adjust:</span>
          <button class="btn-quick-edit" data-edit="Move the dentist to Monday">Move dentist to Monday</button>
          <button class="btn-quick-edit" data-edit="Leave 15 minutes earlier">Leave 15m earlier</button>
          <button class="btn-quick-edit" data-edit="Add folding chairs to packing list">+ Folding chairs</button>
        </div>
        `
            : ''
        }
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

  const timePillHtml = plan.leave_by
    ? isCancellation
      ? `<span class="plan-time-pill" style="border-color: rgba(239, 68, 68, 0.35); color: #fca5a5;">⏰ Scheduled: ${escapeHtml(formattedLeaveTime)}</span>`
      : `<span class="plan-time-pill">🚗 Depart ${escapeHtml(formattedLeaveTime)}</span>`
    : '';

  return `
    <div class="plan-card-widget ${statusClass} ${isCancellation ? 'cancellation-card' : ''}" id="card-${plan.id}">
      <div class="card-header">
        <div class="card-title-group">
          <div class="card-title">${escapeHtml(plan.title)}</div>
          <div class="card-date-sub">
            <span class="plan-date-pill">📅 ${escapeHtml(formattedTargetDate)}</span>
            ${timePillHtml}
          </div>
        </div>
        <span class="card-status-badge ${statusClass}">${statusLabel}</span>
      </div>

      ${conflictHtml}

      ${
        !isCancellation
          ? `
      <div class="plan-metrics-grid">
        <div class="metric-tile">
          <div class="metric-label">🚗 Recommended Departure</div>
          <div class="metric-value">Leave by ${escapeHtml(formattedLeaveTime)}</div>
          <div class="metric-detail">📅 ${escapeHtml(formatDate(plan.leave_by || plan.target_date))} · Travel & buffer included</div>
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
      `
          : ''
      }

      ${rescheduledEventsHtml}

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
