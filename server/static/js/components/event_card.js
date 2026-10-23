/**
 * Event Detail Card Component: Renders a dedicated, glassmorphic detail view
 * for any saved calendar event, displaying attendees, priority level, location,
 * description notes, and required gear checklists with actionable buttons.
 */
import { formatEventDateTime, formatDate } from '../datetime.js';

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function renderEventDetailCardHtml(event) {
  if (!event) return '';

  const title = event.title || 'Untitled Event';
  const attendees = event.attendees || [];
  const requiredItems = event.required_items || [];
  const description = event.description || '';
  const priority = Number(event.priority) || 1;

  // Format Date and Time
  const dtInfo = formatEventDateTime(event.start_time, event.end_time);

  // Category Icon
  let icon = '📅';
  const lowerTitle = title.toLowerCase();
  if (lowerTitle.includes('soccer') || lowerTitle.includes('tournament') || lowerTitle.includes('game') || lowerTitle.includes('match')) icon = '⚽';
  else if (lowerTitle.includes('dentist') || lowerTitle.includes('doctor') || lowerTitle.includes('clinic')) icon = '🦷';
  else if (lowerTitle.includes('grocery') || lowerTitle.includes('market') || lowerTitle.includes('store') || lowerTitle.includes('shopping')) icon = '🛒';
  else if (lowerTitle.includes('party') || lowerTitle.includes('birthday') || lowerTitle.includes('dinner')) icon = '🎉';
  else if (lowerTitle.includes('contest') || lowerTitle.includes('codeforces') || lowerTitle.includes('hackathon') || lowerTitle.includes('zoom')) icon = '💻';

  // Priority Label and Badge
  let priorityLabel = 'Routine / Flexible';
  let priorityClass = 'priority-routine';
  if (priority === 2) {
    priorityLabel = 'Important';
    priorityClass = 'priority-important';
  } else if (priority >= 3) {
    priorityLabel = 'Fixed / High Priority';
    priorityClass = 'priority-high';
  }

  // Location display
  let locationName = '';
  let coordsDisplay = '';
  if (event.location && typeof event.location === 'object') {
    locationName = event.location.name || '';
    if (event.location.latitude && event.location.longitude) {
      coordsDisplay = `${event.location.latitude.toFixed(4)}°, ${event.location.longitude.toFixed(4)}°`;
    }
  } else if (event.location_name) {
    locationName = event.location_name;
  } else if (typeof event.location === 'string') {
    locationName = event.location;
  }

  // Attendees chips
  let attendeesHtml = '';
  if (attendees.length > 0) {
    attendeesHtml = `
      <div class="event-detail-section">
        <div class="detail-section-label">👥 Attendees</div>
        <div class="attendees-chip-list">
          ${attendees.map((a) => `<span class="attendee-chip">👤 ${escapeHtml(a)}</span>`).join('')}
        </div>
      </div>
    `;
  }

  // Required Items Checklist
  let gearHtml = '';
  if (requiredItems.length > 0) {
    gearHtml = `
      <div class="event-detail-section">
        <div class="detail-section-label">🎒 Required Gear & Checklist</div>
        <div class="event-gear-list">
          ${requiredItems.map((item, idx) => `
            <label class="checklist-chip" id="gear_item_${idx}">
              <input type="checkbox" checked />
              <span>${escapeHtml(item)}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Conflict Notice if present
  let conflictBannerHtml = '';
  if (event.has_conflicts && event.conflicts && event.conflicts.length > 0) {
    const c = event.conflicts[0];
    conflictBannerHtml = `
      <div class="conflict-alert-box" style="margin-bottom: 14px;">
        <span class="conflict-icon">⚠️</span>
        <div class="conflict-content">
          <div class="conflict-title">Direct Conflict Detected</div>
          <div class="conflict-desc">${escapeHtml(c.details || 'Overlaps with another family event')}</div>
        </div>
      </div>
    `;
  }

  // Calculate Duration
  let durationStr = '';
  if (event.duration_minutes) {
    const h = Math.floor(event.duration_minutes / 60);
    const m = event.duration_minutes % 60;
    if (h > 0 && m > 0) durationStr = ` (${h}h ${m}m)`;
    else if (h > 0) durationStr = ` (${h} hr${h > 1 ? 's' : ''})`;
    else if (m > 0) durationStr = ` (${m} mins)`;
  }

  return `
    <div class="event-detail-card" id="event-card-${escapeHtml(event.id || 'current')}">
      <div class="event-detail-header">
        <div class="event-title-group">
          <div class="event-detail-title">
            <span class="event-detail-icon">${icon}</span>
            <span>${escapeHtml(title)}</span>
          </div>
          <div class="event-meta-pills">
            <span class="event-date-pill">📅 ${escapeHtml(dtInfo.dateStr)}</span>
            <span class="event-time-pill">⏰ ${escapeHtml(dtInfo.timeStr)}${escapeHtml(durationStr)}</span>
          </div>
        </div>
        <span class="event-priority-badge ${priorityClass}">${priorityLabel}</span>
      </div>

      ${conflictBannerHtml}

      ${locationName ? `
        <div class="event-detail-location">
          <span class="location-icon">📍</span>
          <div class="location-info">
            <div class="location-name">${escapeHtml(locationName)}</div>
            ${coordsDisplay ? `<div class="location-coords">GPS: ${escapeHtml(coordsDisplay)}</div>` : ''}
          </div>
        </div>
      ` : ''}

      ${description ? `
        <div class="event-detail-description">
          <div class="detail-section-label">📝 Description & Notes</div>
          <div class="description-text">${escapeHtml(description)}</div>
        </div>
      ` : ''}

      ${attendeesHtml}

      ${gearHtml}

      <div class="event-card-actions">
        <button class="btn-event-action reschedule" data-action="Reschedule ${escapeHtml(title)}">
          <span>🔄</span> Reschedule
        </button>
        <button class="btn-event-action cancel" data-action="Cancel ${escapeHtml(title)} on ${escapeHtml(dtInfo.dateStr)}">
          <span>🗑️</span> Cancel Event
        </button>
        ${locationName ? `
          <button class="btn-event-action weather" data-action="Weather forecast for ${escapeHtml(locationName)} on ${escapeHtml(dtInfo.dateStr)}">
            <span>🌤️</span> Check Weather
          </button>
        ` : ''}
      </div>
    </div>
  `;
}

export function bindEventCardActions(containerEl, onActionTrigger) {
  if (!containerEl || !onActionTrigger) return;

  containerEl.querySelectorAll('.btn-event-action').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const action = btn.getAttribute('data-action');
      if (action) {
        onActionTrigger(action);
      }
    };
  });
}
