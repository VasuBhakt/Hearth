/**
 * Chat Stage Component: Renders user & assistant conversations, interactive plan briefing cards,
 * interactive schedule cards, and handles user input submission.
 */
import { stateStore } from '../state.js';
import { renderPlanCardHtml, bindPlanCardEvents } from './plan_card.js';
import { renderEventDetailCardHtml, bindEventCardActions } from './event_card.js';
import { formatEventDateTime } from '../datetime.js';

export function initChatStage(elements, onSendMessage) {
  const { feedEl, inputEl, btnSendEl } = elements;
  if (!feedEl || !inputEl || !btnSendEl) return;

  // React to reactive state updates
  stateStore.subscribe((state) => {
    renderMessages(feedEl, state.messages, state.isThinking, (editPrompt) => {
      if (onSendMessage) {
        onSendMessage(editPrompt);
      }
    });

    btnSendEl.disabled = state.isThinking;
    inputEl.disabled = state.isThinking;
  });

  // Handle send action
  function submitInput() {
    const text = inputEl.value.trim();
    if (!text || stateStore.getState().isThinking) return;

    inputEl.value = '';
    if (onSendMessage) {
      onSendMessage(text);
    }
  }

  btnSendEl.addEventListener('click', submitInput);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitInput();
    }
  });
}

/**
 * Renders message rows into the chat feed container.
 */
function renderMessages(feedEl, messages, isThinking, onActionTrigger) {
  let html = '';

  for (const msg of messages) {
    const isUser = msg.role === 'user';
    const avatar = isUser ? '👤' : '🔥';
    const roleClass = isUser ? 'user' : 'assistant';

    let contentHtml = `<div class="message-bubble">${formatMessageText(msg.text)}</div>`;

    // Embed Plan Card widget if message has a plan attached
    if (msg.plan) {
      contentHtml = `
        <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
          ${msg.text ? `<div class="message-bubble">${formatMessageText(msg.text)}</div>` : ''}
          ${renderPlanCardHtml(msg.plan)}
        </div>
      `;
    }
    // Embed Event Detail Card widget if message has an event attached
    else if (msg.event) {
      contentHtml = `
        <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
          ${msg.text ? `<div class="message-bubble">${formatMessageText(msg.text)}</div>` : ''}
          ${renderEventDetailCardHtml(msg.event)}
        </div>
      `;
    }
    // Embed Schedule Card widget if message has a schedule attached
    else if (msg.schedule && msg.schedule.events && msg.schedule.events.length > 0) {
      contentHtml = `
        <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
          ${msg.text ? `<div class="message-bubble">${formatMessageText(msg.text)}</div>` : ''}
          ${renderScheduleCardHtml(msg.schedule)}
        </div>
      `;
    }

    html += `
      <div class="chat-row ${roleClass}" id="${msg.id}">
        <div class="chat-avatar">${avatar}</div>
        <div style="display: flex; flex-direction: column; max-width: calc(100% - 50px);">
          ${contentHtml}
          <div class="message-time">${escapeHtml(msg.timestamp || '')}</div>
        </div>
      </div>
    `;
  }

  // If assistant is planning / calling MCP tools, show ambient skeleton
  if (isThinking) {
    html += `
      <div class="chat-row assistant thinking-row">
        <div class="chat-avatar">🔥</div>
        <div class="thinking-indicator">
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
        </div>
      </div>
    `;
  }

  feedEl.innerHTML = html;

  // Bind interactive buttons on Plan Cards (Approve, Undo, Quick Edit)
  bindPlanCardEvents(feedEl, onActionTrigger);

  // Bind interactive actions on Event Detail Cards
  bindEventCardActions(feedEl, onActionTrigger);

  // Bind interactive inspect clicks on Schedule items
  feedEl.querySelectorAll('.schedule-event-item').forEach((item) => {
    item.onclick = (e) => {
      // Don't trigger if clicked on a resolve button or internal control
      if (e.target.closest('.btn-schedule-resolve')) return;
      const title = item.getAttribute('data-event-title');
      if (title && onActionTrigger) {
        onActionTrigger(`Show details for ${title}`);
      }
    };
  });

  // Bind interactive buttons on Schedule Cards
  feedEl.querySelectorAll('.btn-schedule-resolve').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const action = btn.getAttribute('data-action') || "Get us ready for Saturday's tournament";
      if (onActionTrigger) {
        onActionTrigger(action);
      }
    };
  });

  // Auto scroll to latest update with slight timeout for full DOM render
  setTimeout(() => {
    feedEl.scrollTop = feedEl.scrollHeight;
  }, 40);
}

/**
 * Renders a glassmorphic Schedule Briefing Card widget with conflict callouts.
 */
function renderScheduleCardHtml(schedule) {
  const events = schedule.events || [];
  const conflicts = schedule.conflicts || [];
  const hasConflicts = conflicts.length > 0;

  let eventsListHtml = '';
  for (const ev of events) {
    const title = ev.title || 'Untitled Event';
    const loc = (ev.location && ev.location.name) ? ev.location.name : (ev.location_name || (typeof ev.location === 'string' ? ev.location : ''));
    const dtInfo = formatEventDateTime(ev.start_time, ev.end_time);

    // Pick an appropriate icon
    let icon = '📅';
    const lowerTitle = title.toLowerCase();
    if (lowerTitle.includes('soccer') || lowerTitle.includes('tournament') || lowerTitle.includes('game')) icon = '⚽';
    else if (lowerTitle.includes('dentist') || lowerTitle.includes('doctor') || lowerTitle.includes('clinic')) icon = '🦷';
    else if (lowerTitle.includes('grocery') || lowerTitle.includes('market') || lowerTitle.includes('store')) icon = '🛒';
    else if (lowerTitle.includes('party') || lowerTitle.includes('birthday')) icon = '🎉';
    else if (lowerTitle.includes('contest') || lowerTitle.includes('codeforces') || lowerTitle.includes('hackathon')) icon = '💻';

    // Check if this event participates in any conflict
    const clashingConflict = conflicts.find((c) => {
      const details = (c.details || '').toLowerCase();
      return (
        c.event1_id === ev.id ||
        c.event2_id === ev.id ||
        (c.event_a_id && c.event_a_id === ev.id) ||
        (c.event_b_id && c.event_b_id === ev.id) ||
        details.includes(title.toLowerCase())
      );
    });

    const isConflict = !!clashingConflict;
    const itemClass = isConflict ? 'schedule-event-item has-conflict' : 'schedule-event-item';

    let conflictAlertHtml = '';
    if (isConflict) {
      conflictAlertHtml = `
        <div class="schedule-conflict-alert">
          <span>⚠️ DIRECT SCHEDULE CLASH:</span>
          <span>${escapeHtml(clashingConflict.details)}</span>
        </div>
      `;
    }

    eventsListHtml += `
      <div class="${itemClass}" data-event-title="${escapeHtml(title)}" title="Click to view full event details">
        <div class="schedule-event-top">
          <div class="schedule-event-title">
            <span class="schedule-event-icon">${icon}</span>
            <span class="schedule-event-name">${escapeHtml(title)}</span>
          </div>
          <div class="schedule-event-datetime">
            <span class="schedule-event-date" title="Event Date">📅 ${escapeHtml(dtInfo.dateStr)}</span>
            <span class="schedule-event-time" title="Event Time Window">⏰ ${escapeHtml(dtInfo.timeStr)}</span>
            <span class="schedule-event-inspect-btn">🔍 View</span>
          </div>
        </div>
        ${loc ? `<div class="schedule-event-meta">📍 ${escapeHtml(loc)}</div>` : ''}
        ${conflictAlertHtml}
      </div>
    `;
  }

  let actionButtonHtml = '';
  if (hasConflicts) {
    const buttons = conflicts.map((c) => {
      const ev1 = events.find((e) => e.id === (c.event1_id || c.event_a_id));
      const ev2 = events.find((e) => e.id === (c.event2_id || c.event_b_id));

      let promptAction = "Resolve schedule conflict";
      let buttonLabel = "Resolve Schedule Conflict";

      if (ev1 && ev2) {
        const higher = (ev1.priority || 1) >= (ev2.priority || 1) ? ev1 : ev2;
        const lower = (ev1.priority || 1) >= (ev2.priority || 1) ? ev2 : ev1;
        promptAction = `Resolve schedule conflict: reschedule ${lower.title} to free up ${higher.title}`;
        buttonLabel = `Resolve Conflict: Reschedule ${lower.title}`;
      } else if (c.details) {
        promptAction = `Resolve schedule conflict: ${c.details}`;
        buttonLabel = `Resolve Schedule Conflict (${c.conflict_type || 'Overlap'})`;
      }

      return `
        <button class="btn-schedule-resolve" data-action="${escapeHtml(promptAction)}">
          <span>⚡</span>
          <span>${escapeHtml(buttonLabel)}</span>
        </button>
      `;
    }).join('');

    actionButtonHtml = `
      <div class="schedule-actions-row">
        ${buttons}
      </div>
    `;
  }

  return `
    <div class="schedule-card-widget">
      <div class="schedule-card-header">
        <div class="schedule-card-title">
          <span>📅</span>
          <span>Household Schedule Overview</span>
        </div>
        <span class="schedule-card-badge">${events.length} Events ${hasConflicts ? `· ⚠️ ${conflicts.length} Conflict${conflicts.length > 1 ? 's' : ''}` : ''}</span>
      </div>

      <div class="schedule-events-list">
        ${eventsListHtml}
      </div>

      ${actionButtonHtml}
    </div>
  `;
}

function formatMessageText(text) {
  if (!text) return '';
  let safe = escapeHtml(text);
  // Support **bold**
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  return safe;
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
