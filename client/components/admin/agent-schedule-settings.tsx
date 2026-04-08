'use client';

import { useMemo } from 'react';
import { Clock, Copy } from 'lucide-react';
import type { OnlineSchedule } from '@/contexts/OnlineScheduleContext';

/** JS weekday: 0 Sun … 6 Sat. Display order Mon → Sun. */
const DAY_CHIPS: { dow: number; short: string }[] = [
  { dow: 1, short: 'MON' },
  { dow: 2, short: 'TUE' },
  { dow: 3, short: 'WED' },
  { dow: 4, short: 'THU' },
  { dow: 5, short: 'FRI' },
  { dow: 6, short: 'SAT' },
  { dow: 0, short: 'SUN' },
];

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return (Number.isFinite(h) ? h : 0) * 60 + (Number.isFinite(m) ? m : 0);
}

function formatTime12h(t: string): string {
  const [h, m] = t.split(':').map(Number);
  const hh = Number.isFinite(h) ? h : 0;
  const mm = Number.isFinite(m) ? m : 0;
  const d = new Date();
  d.setHours(hh, mm, 0, 0);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function sortDays(days: number[]): number[] {
  return [...days].sort((a, b) => a - b);
}

function ensureAtLeastOneDay(days: number[]): number[] {
  return days.length > 0 ? sortDays(days) : [1];
}

export interface AgentScheduleSettingsProps {
  value: OnlineSchedule;
  onChange: (next: OnlineSchedule) => void;
}

export function AgentScheduleSettings({ value, onChange }: AgentScheduleSettingsProps) {
  const { workingDays, startTime, endTime } = value;

  const preview = useMemo(() => {
    const startM = timeToMinutes(startTime);
    const endM = timeToMinutes(endTime);
    if (endM <= startM) {
      return { leftPct: 0, widthPct: 0, invalid: true as const };
    }
    const leftPct = (startM / 1440) * 100;
    const widthPct = ((endM - startM) / 1440) * 100;
    return { leftPct, widthPct, invalid: false as const };
  }, [startTime, endTime]);

  const activeDayLabels = useMemo(() => {
    const order = [1, 2, 3, 4, 5, 6, 0];
    const labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return order.filter((d) => workingDays.includes(d)).map((d) => labels[d]);
  }, [workingDays]);

  const toggleDay = (dow: number) => {
    const on = workingDays.includes(dow);
    const next = on
      ? workingDays.filter((d) => d !== dow)
      : [...workingDays, dow];
    onChange({ ...value, workingDays: ensureAtLeastOneDay(next) });
  };

  const applyPreset = (preset: 'standard' | 'extended' | '247' | 'custom') => {
    if (preset === 'custom') return;
    if (preset === 'standard') {
      onChange({ workingDays: [1, 2, 3, 4, 5], startTime: '09:00', endTime: '17:00' });
      return;
    }
    if (preset === 'extended') {
      onChange({ workingDays: [1, 2, 3, 4, 5], startTime: '09:00', endTime: '21:00' });
      return;
    }
    onChange({ workingDays: [0, 1, 2, 3, 4, 5, 6], startTime: '00:00', endTime: '23:59' });
  };

  const copyWeekdays = () => {
    onChange({ ...value, workingDays: ensureAtLeastOneDay([1, 2, 3, 4, 5]) });
  };

  const copyFullWeek = () => {
    onChange({ ...value, workingDays: [0, 1, 2, 3, 4, 5, 6] });
  };

  const copyWeekendsOnly = () => {
    onChange({ ...value, workingDays: ensureAtLeastOneDay([0, 6]) });
  };

  /** If Monday is on, turn on Tue–Fri as well (same hours). */
  const copyMondayToWeekdays = () => {
    if (!workingDays.includes(1)) return;
    const merged = new Set([...workingDays, 2, 3, 4, 5]);
    onChange({ ...value, workingDays: sortDays([...merged]) });
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium text-text-primary mb-2">Quick set</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => applyPreset('standard')}
            className="rounded-full border border-border bg-white px-3 py-1.5 text-xs font-medium text-text-primary shadow-sm hover:border-primary/40 hover:bg-primary/5 transition-colors"
          >
            Standard (9–5)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('extended')}
            className="rounded-full border border-border bg-white px-3 py-1.5 text-xs font-medium text-text-primary shadow-sm hover:border-primary/40 hover:bg-primary/5 transition-colors"
          >
            Extended (9–9)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('247')}
            className="rounded-full border border-border bg-white px-3 py-1.5 text-xs font-medium text-text-primary shadow-sm hover:border-primary/40 hover:bg-primary/5 transition-colors"
          >
            24/7
          </button>
          <span className="inline-flex items-center rounded-full border border-dashed border-border/80 bg-panel/50 px-3 py-1.5 text-xs text-text-muted">
            Custom — edit below
          </span>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-text-primary mb-2">Working days</p>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
          {DAY_CHIPS.map(({ dow, short }) => {
            const active = workingDays.includes(dow);
            return (
              <button
                key={dow}
                type="button"
                role="switch"
                aria-checked={active}
                onClick={() => toggleDay(dow)}
                className={[
                  'flex flex-col items-center justify-center rounded-xl border-2 px-1 py-3 text-center transition-all min-h-[4.5rem]',
                  active
                    ? 'border-primary bg-primary/10 shadow-sm ring-1 ring-primary/20'
                    : 'border-border/80 bg-white hover:border-border hover:bg-slate-50/80',
                ].join(' ')}
              >
                <span
                  className={`text-[11px] font-bold tracking-wide ${active ? 'text-primary' : 'text-text-muted'}`}
                >
                  {short}
                </span>
                <span
                  className={`mt-1.5 text-[10px] font-semibold uppercase ${active ? 'text-primary' : 'text-text-secondary'}`}
                >
                  {active ? 'On' : 'Off'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-text-primary mb-1.5">
            <Clock className="h-3.5 w-3.5 text-text-muted" aria-hidden />
            Start time
          </label>
          <input
            type="time"
            value={startTime}
            onChange={(e) => onChange({ ...value, startTime: e.target.value })}
            className="w-full rounded-xl border border-border bg-white px-3 py-2.5 text-sm font-medium text-text-primary shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p className="mt-1 text-[10px] text-text-muted">{formatTime12h(startTime)}</p>
        </div>
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-text-primary mb-1.5">
            <Clock className="h-3.5 w-3.5 text-text-muted" aria-hidden />
            End time
          </label>
          <input
            type="time"
            value={endTime}
            onChange={(e) => onChange({ ...value, endTime: e.target.value })}
            className="w-full rounded-xl border border-border bg-white px-3 py-2.5 text-sm font-medium text-text-primary shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p className="mt-1 text-[10px] text-text-muted">{formatTime12h(endTime)}</p>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-gradient-to-b from-white to-slate-50/90 p-4 shadow-sm">
        <p className="text-xs font-semibold text-text-primary mb-1">Schedule preview</p>
        <p className="text-[11px] text-text-secondary mb-3">
          {activeDayLabels.length > 0
            ? `Applies to ${activeDayLabels.join(', ')} · ${formatTime12h(startTime)} – ${formatTime12h(endTime)}`
            : 'Select at least one day'}
        </p>
        {preview.invalid ? (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200/80 rounded-lg px-3 py-2">
            End time must be after start time for a valid preview.
          </p>
        ) : (
          <>
            <div className="relative h-10 rounded-lg bg-slate-200/80 overflow-hidden ring-1 ring-inset ring-slate-300/40">
              <div
                className="absolute top-0 bottom-0 rounded-md bg-gradient-to-b from-primary/90 to-primary shadow-inner"
                style={{
                  left: `${preview.leftPct}%`,
                  width: `${preview.widthPct}%`,
                  minWidth: preview.widthPct > 0 ? '4px' : undefined,
                }}
              />
            </div>
            <div className="flex justify-between mt-1.5 text-[10px] font-medium text-text-muted tabular-nums">
              <span>12 AM</span>
              <span>6 AM</span>
              <span>12 PM</span>
              <span>6 PM</span>
              <span>12 AM</span>
            </div>
          </>
        )}
      </div>

      <div>
        <p className="text-xs font-medium text-text-primary mb-2 flex items-center gap-1.5">
          <Copy className="h-3.5 w-3.5 text-text-muted" aria-hidden />
          Copy day set
        </p>
        <p className="text-[11px] text-text-secondary mb-2">
          Same hours apply to every active day. Use these to quickly align which days are on.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={copyWeekdays}
            className="rounded-lg border border-border bg-white px-3 py-2 text-xs font-medium text-text-primary hover:bg-slate-50 transition-colors"
          >
            Mon–Fri
          </button>
          <button
            type="button"
            onClick={copyFullWeek}
            className="rounded-lg border border-border bg-white px-3 py-2 text-xs font-medium text-text-primary hover:bg-slate-50 transition-colors"
          >
            Every day
          </button>
          <button
            type="button"
            onClick={copyWeekendsOnly}
            className="rounded-lg border border-border bg-white px-3 py-2 text-xs font-medium text-text-primary hover:bg-slate-50 transition-colors"
          >
            Weekend only
          </button>
          <button
            type="button"
            onClick={copyMondayToWeekdays}
            disabled={!workingDays.includes(1)}
            title={workingDays.includes(1) ? 'Turn on Tue–Fri to match Monday' : 'Turn Monday on first'}
            className="rounded-lg border border-border bg-white px-3 py-2 text-xs font-medium text-text-primary hover:bg-slate-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Mon on → add Tue–Fri
          </button>
        </div>
      </div>
    </div>
  );
}
