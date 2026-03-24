'use client';

import { useMemo, useState, useCallback } from 'react';

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

function formatDate(d: Date): string {
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
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

/** Stable mock: per-day hours worked and sessions from agentId. Replace with API. Exported for PDF reports. Uses March–today window. */
export function getDayAttendance(agentId: string, workingDays: number[]): DayAttendance[] {
  const { firstSunday, totalDays } = getAttendanceWindow();
  const workingSet = new Set(workingDays);
  const out: DayAttendance[] = [];
  let seed = agentId.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const WORK_START = 9 * 60; // 9:00
  const WORK_END = 18 * 60;   // 18:00

  for (let i = 0; i < totalDays; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const date = getDateForIndex(i, firstSunday);
    const isOff = !workingSet.has(date.getDay());
    if (isOff) {
      out.push({ date, hoursWorked: 0, sessions: [] });
      continue;
    }
    const present = (seed % 10) >= 3;
    if (!present) {
      out.push({ date, hoursWorked: 0, sessions: [] });
      continue;
    }
    // 2–8 hours for the day
    const totalMinutes = 60 * (2 + (seed % 7));
    const numSessions = (seed % 5) >= 3 ? 2 : 1;
    const sessions: DaySession[] = [];
    if (numSessions === 1) {
      const start = WORK_START + (seed % 60);
      const end = Math.min(WORK_END, start + totalMinutes);
      sessions.push({ startMinutes: start, endMinutes: end });
    } else {
      const half = Math.floor(totalMinutes / 2);
      const start1 = WORK_START + (seed % 45);
      const end1 = start1 + half;
      const start2 = end1 + 30 + (seed % 30);
      const end2 = Math.min(WORK_END, start2 + totalMinutes - half);
      sessions.push({ startMinutes: start1, endMinutes: end1 });
      if (end2 > start2) sessions.push({ startMinutes: start2, endMinutes: end2 });
    }
    const actualMinutes = sessions.reduce((s, x) => s + (x.endMinutes - x.startMinutes), 0);
    out.push({
      date,
      hoursWorked: Math.round(actualMinutes) / 60,
      sessions,
    });
  }
  return out;
}

/** Returns per-day attendance and average daily online hours (working days only). */
export function useAgentAttendanceData(
  agentId: string | undefined,
  workingDays: number[] = [1, 2, 3, 4, 5, 6]
): { dayData: DayAttendance[]; averageDailyHours: number } {
  return useMemo(() => {
    if (!agentId) return { dayData: [], averageDailyHours: 0 };
    const dayData = getDayAttendance(agentId, workingDays);
    const workingSet = new Set(workingDays);
    const withHours = dayData.filter(
      (d) => workingSet.has(d.date.getDay()) && d.hoursWorked > 0
    );
    const totalHours = withHours.reduce((s, d) => s + d.hoursWorked, 0);
    const averageDailyHours = withHours.length > 0 ? totalHours / withHours.length : 0;
    return { dayData, averageDailyHours };
  }, [agentId, workingDays]);
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
}: {
  agentId: string;
  workingDays?: number[];
  dayData: DayAttendance[];
}) {
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);

  const { dayLabels, monthLabels, isOffDay, columns } = useMemo(() => {
    const { firstSunday, totalDays, columns: cols } = getAttendanceWindow();
    const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const monthLabels: { col: number; label: string }[] = [];
    let lastMonth = -1;
    for (let col = 0; col < cols; col++) {
      const date = getDateForIndex(col * DAYS_PER_WEEK, firstSunday);
      const month = date.getMonth();
      if (month !== lastMonth) {
        monthLabels.push({ col, label: date.toLocaleDateString(undefined, { month: 'short' }) });
        lastMonth = month;
      }
    }
    const workingSet = new Set(workingDays);
    const isOffDay = (index: number) => !workingSet.has(getDateForIndex(index, firstSunday).getDay());
    return { dayLabels, monthLabels, isOffDay, columns: cols };
  }, [workingDays]);

  const selectedDay = selectedDayIndex != null ? dayData[selectedDayIndex] : null;

  const tooltipForDay = useCallback((d: DayAttendance, index: number) => {
    if (isOffDay(index)) return `${formatDate(d.date)} · Off day (holiday)`;
    if (d.sessions.length === 0) return `${formatDate(d.date)} · No time logged`;
    const first = d.sessions[0];
    const last = d.sessions[d.sessions.length - 1];
    const totalM = d.sessions.reduce((s, x) => s + (x.endMinutes - x.startMinutes), 0);
    return `${formatDate(d.date)} — Online for ${formatDurationMinutes(totalM)} (${formatTimeFromMinutes(first.startMinutes)} – ${formatTimeFromMinutes(last.endMinutes)})`;
  }, [isOffDay]);

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
            Daily Activity — {formatDate(selectedDay.date)}
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
