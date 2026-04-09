'use client';

import { useMemo, useState, useCallback, useEffect } from 'react';
import {
  dateKeyInTimeZone,
  DEFAULT_TENANT_TIMEZONE,
  clockMinutesInTimeZone,
  weekdayInTimeZone,
} from '@/lib/tenant-time';

const DAYS_PER_WEEK = 7;
const CELL_BASE = 'rounded-sm';

export type DaySession = { startMinutes: number; endMinutes: number };

export type DayAttendance = {
  date: Date;
  hoursWorked: number;
  sessions: DaySession[];
};

/** Rolling window: last 7 months from today. Updates as time passes. */
function getAttendanceWindow(): { firstSunday: Date; totalDays: number; columns: number } {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const startDate = new Date(today);
  startDate.setMonth(startDate.getMonth() - 7);
  startDate.setHours(0, 0, 0, 0);
  const firstSunday = new Date(startDate);
  firstSunday.setDate(firstSunday.getDate() - startDate.getDay());
  const endTime = today.getTime();
  const startTime = firstSunday.getTime();
  const totalDaysFromFirstSunday = Math.ceil((endTime - startTime) / 86400000) + 1;
  const columns = Math.ceil(totalDaysFromFirstSunday / DAYS_PER_WEEK);
  const totalDays = columns * DAYS_PER_WEEK;
  return { firstSunday, totalDays, columns };
}

function getDateForIndex(index: number, firstSunday: Date): Date {
  const d = new Date(firstSunday);
  d.setDate(d.getDate() + index);
  return d;
}

function formatDate(d: Date, timeZone: string): string {
  return d.toLocaleDateString('en-US', { timeZone, month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatTimeFromMinutes(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  const period = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:${min.toString().padStart(2, '0')} ${period}`;
}

export function formatDurationMinutes(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** Zero-filled attendance grid for the rolling attendance window. */
export function getDayAttendance(
  _agentId: string,
  workingDays: number[],
  _timeZone: string = DEFAULT_TENANT_TIMEZONE,
): DayAttendance[] {
  const { firstSunday, totalDays } = getAttendanceWindow();
  const workingSet = new Set(workingDays);
  const out: DayAttendance[] = [];

  for (let i = 0; i < totalDays; i++) {
    const date = getDateForIndex(i, firstSunday);
    const isOff = !workingSet.has(date.getDay());
    out.push({ date, hoursWorked: 0, sessions: isOff ? [] : [] });
  }
  return out;
}

/** Returns per-day attendance and average daily online hours (working days only). */
export function useAgentAttendanceData(
  agentId: string | undefined,
  workingDays: number[] = [1, 2, 3, 4, 5, 6],
  timeZone: string = DEFAULT_TENANT_TIMEZONE,
): { dayData: DayAttendance[]; averageDailyHours: number } {
  const API_BASE =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    'https://arabia-dropshipping.onrender.com';
  const TENANT_ID = 1;
  const [dayData, setDayData] = useState<DayAttendance[]>([]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!agentId) {
        setDayData([]);
        return;
      }
      try {
        const url = new URL(`${API_BASE}/api/routing/agents/${Number(agentId)}/attendance`);
        url.searchParams.set('tenant_id', String(TENANT_ID));
        url.searchParams.set('days', '240');
        const res = await fetch(url.toString());
        if (!res.ok) throw new Error('attendance fetch failed');
        const data = (await res.json()) as {
          days: Array<{
            date: string;
            total_minutes: number;
            sessions: Array<{ start_at: string; end_at: string | null }>;
          }>;
        };
        const localBucket = new Map<string, { minutes: number; sessions: DaySession[] }>();
        for (const day of data.days || []) {
          const key = String(day.date || '');
          if (!key) continue;
          const existing = localBucket.get(key) || { minutes: 0, sessions: [] };
          for (const s of day.sessions || []) {
            const st = new Date(s.start_at);
            const en = new Date(s.end_at || new Date().toISOString());
            const startMinutes = clockMinutesInTimeZone(st, timeZone);
            const endMinutes = clockMinutesInTimeZone(en, timeZone);
            const delta = Math.max(0, Math.floor((en.getTime() - st.getTime()) / 60000));
            existing.minutes += delta;
            existing.sessions.push({ startMinutes, endMinutes });
          }
          localBucket.set(key, existing);
        }
        const base = getDayAttendance(agentId, workingDays, timeZone).map((d) => {
          const key = dateKeyInTimeZone(d.date, timeZone);
          const real = localBucket.get(key);
          if (!real) return { ...d, hoursWorked: 0, sessions: [] };
          return {
            ...d,
            hoursWorked: Math.round((real.minutes / 60) * 100) / 100,
            sessions: real.sessions,
          };
        });
        if (!cancelled) setDayData(base);
      } catch {
        if (!cancelled) setDayData(getDayAttendance(agentId, workingDays, timeZone));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [agentId, workingDays, timeZone]);

  const averageDailyHours = useMemo(() => {
    if (!agentId) return 0;
    const workingSet = new Set(workingDays);
    const withHours = dayData.filter(
      (d) => workingSet.has(d.date.getDay()) && d.hoursWorked > 0
    );
    const totalHours = withHours.reduce((s, d) => s + d.hoursWorked, 0);
    return withHours.length > 0 ? totalHours / withHours.length : 0;
  }, [agentId, dayData, workingDays]);

  return { dayData, averageDailyHours };
}

function heatmapColor(hoursWorked: number, isOffDay: boolean): string {
  if (isOffDay) return 'bg-[#ebedf0] opacity-70';
  if (hoursWorked <= 0) return 'bg-[#ebedf0] hover:bg-[#e0e2e6]';
  if (hoursWorked < 2) return 'bg-red-200 hover:bg-red-300';
  if (hoursWorked < 4) return 'bg-red-300 hover:bg-red-400';
  if (hoursWorked < 6) return 'bg-red-500 hover:bg-red-600';
  return 'bg-red-700 hover:bg-red-800';
}

/** workingDays: 0=Sun, 1=Mon, ... 6=Sat. */
export function AgentActivityBar({
  agentId,
  workingDays = [1, 2, 3, 4, 5, 6],
  dayData,
  timeZone = DEFAULT_TENANT_TIMEZONE,
}: {
  agentId: string;
  workingDays?: number[];
  dayData: DayAttendance[];
  timeZone?: string;
}) {
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);

  const { dayLabels, monthLabels, isOffDay, columns } = useMemo(() => {
    const { firstSunday, totalDays, columns: cols } = getAttendanceWindow();
    const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const monthLabels: { col: number; label: string }[] = [];
    let lastMonthKey = '';
    for (let col = 0; col < cols; col++) {
      const date = getDateForIndex(col * DAYS_PER_WEEK, firstSunday);
      const monthKey = new Intl.DateTimeFormat('en-US', {
        timeZone,
        month: 'numeric',
        year: 'numeric',
      }).format(date);
      if (monthKey !== lastMonthKey) {
        monthLabels.push({
          col,
          label: date.toLocaleDateString('en-US', { timeZone, month: 'short' }),
        });
        lastMonthKey = monthKey;
      }
    }
    const workingSet = new Set(workingDays);
    const isOffDay = (index: number) =>
      !workingSet.has(weekdayInTimeZone(getDateForIndex(index, firstSunday), timeZone));
    return { dayLabels, monthLabels, isOffDay, columns: cols };
  }, [workingDays, timeZone]);

  const selectedDay = selectedDayIndex != null ? dayData[selectedDayIndex] : null;

  const tooltipForDay = useCallback(
    (d: DayAttendance, index: number) => {
      if (isOffDay(index)) return `${formatDate(d.date, timeZone)} · Off day (holiday)`;
      if (d.sessions.length === 0) return `${formatDate(d.date, timeZone)} · No time logged`;
      const first = d.sessions[0];
      const last = d.sessions[d.sessions.length - 1];
      const totalM = d.sessions.reduce((s, x) => s + (x.endMinutes - x.startMinutes), 0);
      return `${formatDate(d.date, timeZone)} — Online for ${formatDurationMinutes(totalM)} (${formatTimeFromMinutes(first.startMinutes)} – ${formatTimeFromMinutes(last.endMinutes)})`;
    },
    [isOffDay, timeZone],
  );

  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0 space-y-4">
      {/* Heatmap */}
      <div className="flex flex-1 min-h-0 min-w-0 gap-1">
        <div className="flex flex-col justify-around text-[10px] text-text-muted pr-2 shrink-0">
          <span className="h-4 flex items-center opacity-0" aria-hidden>&nbsp;</span>
          {dayLabels.map((label) => (
            <span key={label} className="h-4 flex items-center">{label}</span>
          ))}
        </div>
        <div className="flex flex-col gap-0.5 flex-1 min-w-0 min-h-[100px]">
          <div className="flex gap-0.5 w-full">
            {Array.from({ length: columns }, (_, col) => {
              const label = monthLabels.find((m) => m.col === col);
              return (
                <div
                  key={col}
                  className={`${CELL_BASE} flex-1 min-w-0 flex items-center justify-center text-[9px] text-text-muted font-medium min-h-[14px]`}
                >
                  {label?.label ?? ''}
                </div>
              );
            })}
          </div>
          <div className="flex gap-0.5 flex-1 min-w-0 w-full min-h-0">
            {Array.from({ length: columns }, (_, col) => (
              <div key={col} className="flex flex-col gap-0.5 flex-1 min-w-0">
                {Array.from({ length: DAYS_PER_WEEK }, (_, row) => {
                  const index = col * DAYS_PER_WEEK + row;
                  const d = dayData[index];
                  const offDay = isOffDay(index);
                  const hours = d?.hoursWorked ?? 0;
                  const title = d ? tooltipForDay(d, index) : '';
                  const isSelected = selectedDayIndex === index;
                  return (
                    <button
                      type="button"
                      key={row}
                      className={`${CELL_BASE} flex-1 min-h-2 min-w-0 cursor-pointer transition-colors border-2 ${heatmapColor(hours, offDay)} ${isSelected ? 'ring-2 ring-primary ring-offset-1 ring-offset-card' : 'border-transparent'}`}
                      title={title}
                      onClick={() => setSelectedDayIndex(index)}
                      aria-label={title}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily Activity Timeline + Session table (when a day is selected) */}
      {selectedDay != null && (
        <div className="space-y-3 border-t border-border pt-4">
          <p className="text-xs font-medium text-text-primary">
            Daily Activity — {formatDate(selectedDay.date, timeZone)}
          </p>
          {/* 24h timeline */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-text-muted w-8">0h</span>
              <div className="flex-1 h-8 bg-[#ebedf0] rounded relative overflow-hidden flex">
                {selectedDay.sessions.map((s, i) => {
                  const left = (s.startMinutes / 1440) * 100;
                  const width = ((s.endMinutes - s.startMinutes) / 1440) * 100;
                  const duration = s.endMinutes - s.startMinutes;
                  const tip = `${formatTimeFromMinutes(s.startMinutes)} – ${formatTimeFromMinutes(s.endMinutes)} (${formatDurationMinutes(duration)})`;
                  return (
                    <div
                      key={i}
                      className="absolute h-full bg-red-500 hover:bg-red-600 transition-colors rounded-sm min-w-[4px]"
                      style={{ left: `${left}%`, width: `${width}%` }}
                      title={tip}
                    />
                  );
                })}
              </div>
              <span className="text-[10px] text-text-muted w-8">24h</span>
            </div>
          </div>

          {/* Session Breakdown table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs border border-border rounded-lg overflow-hidden">
              <thead>
                <tr className="bg-panel border-b border-border">
                  <th className="text-left py-2 px-3 font-medium text-text-muted">Login</th>
                  <th className="text-left py-2 px-3 font-medium text-text-muted">Logout</th>
                  <th className="text-left py-2 px-3 font-medium text-text-muted">Duration</th>
                </tr>
              </thead>
              <tbody>
                {selectedDay.sessions.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-3 px-3 text-text-muted">
                      No sessions this day
                    </td>
                  </tr>
                ) : (
                  selectedDay.sessions.map((s, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td className="py-2 px-3 text-text-primary">
                        {formatTimeFromMinutes(s.startMinutes)}
                      </td>
                      <td className="py-2 px-3 text-text-primary">
                        {formatTimeFromMinutes(s.endMinutes)}
                      </td>
                      <td className="py-2 px-3 text-text-primary">
                        {formatDurationMinutes(s.endMinutes - s.startMinutes)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
