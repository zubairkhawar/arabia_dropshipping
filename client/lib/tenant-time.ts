/** Tenant wall-clock formatting: DB timestamps are UTC; interpret with IANA `timeZone`. */

export const DEFAULT_TENANT_TIMEZONE = 'Asia/Karachi';

/**
 * Parse API datetime strings stored as naive UTC in Postgres.
 * JSON often serializes without `Z`; ECMAScript then treats that as *local* wall time, which
 * shifts attendance and other labels by the browser offset vs UTC.
 */
export function parseBackendUtcDate(iso: string | null | undefined): Date | null {
  if (iso == null || iso === '') return null;
  const s = String(iso).trim();
  if (!s) return null;
  let d: Date;
  if (/[zZ]$/.test(s)) d = new Date(s);
  else if (/[+-]\d{2}:?\d{2}$/.test(s)) d = new Date(s);
  else {
    const normalized = s.includes('T') ? s : s.replace(' ', 'T');
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(normalized)) d = new Date(`${normalized}Z`);
    else d = new Date(s);
  }
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Admin knowledge-base "Last updated" column: dd/mm/yyyy, 24h clock in tenant zone. */
export function formatKnowledgeSourceUpdatedInZone(
  iso: string | null | undefined,
  timeZone: string,
): string {
  const d = parseBackendUtcDate(iso);
  if (!d) return '-';
  return d.toLocaleString('en-GB', {
    timeZone,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** Align PK formats (0321… vs 92321…) for dedupe / “same customer” checks. */
export function normalizePhoneDedupeKey(phone: string | undefined): string | null {
  if (!phone || typeof phone !== 'string') return null;
  let d = phone.replace(/\D/g, '');
  if (!d) return null;
  if (d.length >= 10 && d.startsWith('92')) {
    d = d.slice(-10);
  } else if (d.length === 11 && d.startsWith('0')) {
    d = d.slice(1);
  }
  return d;
}

export function normalizeIanaTimeZone(tz: string | null | undefined): string {
  const raw = (tz ?? DEFAULT_TENANT_TIMEZONE).trim() || DEFAULT_TENANT_TIMEZONE;
  try {
    Intl.DateTimeFormat(undefined, { timeZone: raw }).format(new Date());
    return raw;
  } catch {
    return DEFAULT_TENANT_TIMEZONE;
  }
}

export function dateKeyInTimeZone(d: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

function parseCalendarKey(key: string): [number, number, number] {
  const [y, m, d] = key.split('-').map(Number);
  return [y, m, d];
}

export function addDaysToCalendarKey(key: string, delta: number): string {
  const [y, m, d] = parseCalendarKey(key);
  const u = Date.UTC(y, m - 1, d + delta);
  const x = new Date(u);
  return `${x.getUTCFullYear()}-${String(x.getUTCMonth() + 1).padStart(2, '0')}-${String(x.getUTCDate()).padStart(2, '0')}`;
}

/** Number of calendar days from earlierKey to laterKey (same day → 0). */
export function calendarDaysBetweenEarlierAndLater(earlierKey: string, laterKey: string): number {
  const [y1, m1, d1] = parseCalendarKey(earlierKey);
  const [y2, m2, d2] = parseCalendarKey(laterKey);
  const u1 = Date.UTC(y1, m1 - 1, d1, 12, 0, 0);
  const u2 = Date.UTC(y2, m2 - 1, d2, 12, 0, 0);
  return Math.round((u2 - u1) / 86400000);
}

export function formatTime12hInZone(d: Date, timeZone: string): string {
  return d.toLocaleTimeString('en-US', {
    timeZone,
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

export function formatWeekdayLongInZone(d: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'long' }).format(d);
}

export function formatWeekdayShortMonthDayInZone(d: Date, timeZone: string): string {
  return d.toLocaleDateString('en-US', {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

/** e.g. Apr 5, 3:45 PM (year omitted if same as `now` in zone). */
export function formatOlderMessageDateTimeInZone(d: Date, timeZone: string, now: Date = new Date()): string {
  const yNow = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric' }).format(now);
  const yMsg = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric' }).format(d);
  if (yNow === yMsg) {
    return d.toLocaleString('en-US', {
      timeZone,
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  }
  return d.toLocaleString('en-US', {
    timeZone,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Conversation list / notifications: Today, 10:30 AM · Yesterday, … · Monday, … · Apr 5, …
 */
export function formatConversationListTime(
  iso: string | null | undefined,
  timeZone: string,
  now: Date = new Date(),
): string {
  if (!iso) return '—';
  const d = parseBackendUtcDate(iso) ?? new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const msgKey = dateKeyInTimeZone(d, timeZone);
  const todayKey = dateKeyInTimeZone(now, timeZone);
  const diff = calendarDaysBetweenEarlierAndLater(msgKey, todayKey);
  const time = formatTime12hInZone(d, timeZone);
  if (diff === 0) return `Today, ${time}`;
  if (diff === 1) return `Yesterday, ${time}`;
  if (diff >= 2 && diff <= 7) return `${formatWeekdayLongInZone(d, timeZone)}, ${time}`;
  return formatOlderMessageDateTimeInZone(d, timeZone, now);
}

/** Inline message bubble: time only in tenant zone. */
export function formatMessageBubbleTime(
  iso: string | undefined,
  fallbackLabel: string | undefined,
  timeZone: string,
): string {
  if (iso) {
    const d = parseBackendUtcDate(iso) ?? new Date(iso);
    if (!Number.isNaN(d.getTime())) return formatTime12hInZone(d, timeZone);
  }
  return fallbackLabel ?? '';
}

/** Short "Just now" / "5m ago" then calendar-aware time in zone. */
export function formatCompactActivity(iso: string, timeZone: string, now: Date = new Date()): string {
  const d = parseBackendUtcDate(iso) ?? new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffSec = Math.max(0, (now.getTime() - d.getTime()) / 1000);
  if (diffSec < 60) return 'Just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
  const msgKey = dateKeyInTimeZone(d, timeZone);
  const todayKey = dateKeyInTimeZone(now, timeZone);
  if (msgKey === todayKey) return formatTime12hInZone(d, timeZone);
  return formatConversationListTime(iso, timeZone, now);
}

export function weekdayInTimeZone(d: Date, timeZone: string): number {
  const wd = new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short' }).format(d);
  const map: Record<string, number> = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  };
  return map[wd] ?? 0;
}

export function clockMinutesInTimeZone(d: Date, timeZone: string): number {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = fmt.formatToParts(d);
  let h = 0;
  let m = 0;
  for (const p of parts) {
    if (p.type === 'hour') h = Number(p.value);
    if (p.type === 'minute') m = Number(p.value);
  }
  return h * 60 + m;
}
