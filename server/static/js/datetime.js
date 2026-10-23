/**
 * Datetime formatting utilities for Hearth UI.
 * Handles ISO timestamps and relative times with zero UTC shifting bugs.
 */

/**
 * Parses an ISO string or date-time string into a local Date object.
 * Avoids browser UTC-shift quirks when parsing ISO date-only strings (e.g. "2026-10-17").
 */
export function parseIsoDateTime(isoStr) {
  if (!isoStr) return null;
  const str = String(isoStr).trim();
  const m = str.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (m) {
    const year = parseInt(m[1], 10);
    const month = parseInt(m[2], 10) - 1;
    const day = parseInt(m[3], 10);
    const hour = m[4] != null ? parseInt(m[4], 10) : 0;
    const min = m[5] != null ? parseInt(m[5], 10) : 0;
    const sec = m[6] != null ? parseInt(m[6], 10) : 0;
    return new Date(year, month, day, hour, min, sec);
  }
  const d = new Date(isoStr);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Formats an ISO string to a readable date (e.g., "Sat, Oct 17, 2026").
 */
export function formatDate(isoStr, options = {}) {
  const d = parseIsoDateTime(isoStr);
  if (!d) return isoStr || '';
  const defaultOpts = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  };
  return d.toLocaleDateString(undefined, { ...defaultOpts, ...options });
}

/**
 * Formats an ISO string or time string to a readable 12-hour or local time (e.g., "09:00 AM").
 */
export function formatTime(isoStr) {
  if (!isoStr) return '--:--';
  const str = String(isoStr).trim();
  if (/^\d{2}:\d{2}(:\d{2})?$/.test(str)) {
    const parts = str.split(':');
    const h = parseInt(parts[0], 10);
    const m = parts[1];
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${String(h12).padStart(2, '0')}:${m} ${ampm}`;
  }
  const d = parseIsoDateTime(isoStr);
  if (!d) return isoStr.substring(11, 16) || '--:--';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Formats an event's start and end timestamps into date and time strings.
 * Returns { dateStr, timeStr, fullStr }.
 * E.g., dateStr: "Sat, Oct 17, 2026", timeStr: "09:00 AM – 01:00 PM"
 */
export function formatEventDateTime(startIso, endIso) {
  if (!startIso) return { dateStr: '', timeStr: '', fullStr: '' };

  const startDate = formatDate(startIso);
  const startTime = formatTime(startIso);

  if (!endIso) {
    return {
      dateStr: startDate,
      timeStr: startTime,
      fullStr: `${startDate} · ${startTime}`,
    };
  }

  const endDate = formatDate(endIso);
  const endTime = formatTime(endIso);

  const isSameDay = !endDate || startDate === endDate;
  const dateStr = isSameDay ? startDate : `${startDate} – ${endDate}`;
  const timeStr = `${startTime} – ${endTime}`;

  return {
    dateStr,
    timeStr,
    fullStr: `${dateStr} · ${timeStr}`,
  };
}
