'use client';

import { useMemo } from 'react';

const WEEKS = 26;
const DAYS_PER_WEEK = 7;
const TOTAL_DAYS = WEEKS * DAYS_PER_WEEK;

const CELL_BASE = 'rounded-sm';

/** Generate stable mock attendance (present = true) for each day from agentId. Replace with API data. */
function getAttendancePresent(agentId: string): boolean[] {
  const out: boolean[] = [];
  let seed = agentId.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  for (let i = 0; i < TOTAL_DAYS; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    out.push((seed % 10) >= 3); // ~70% present
  }
  return out;
}

function formatDate(d: Date): string {
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function getDateForIndex(index: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - (TOTAL_DAYS - 1 - index));
  return d;
}

/** workingDays: 0=Sun, 1=Mon, ... 6=Sat. Days not in this array are holidays (attendance not marked). */
export function AgentActivityBar({
  agentId,
  workingDays = [1, 2, 3, 4, 5, 6],
}: {
  agentId: string;
  workingDays?: number[];
}) {
  const { present, dayLabels, monthLabels, isOffDay } = useMemo(() => {
    const rawPresent = getAttendancePresent(agentId);
    const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const monthLabels: { col: number; label: string }[] = [];
    let lastMonth = -1;
    for (let col = 0; col < WEEKS; col++) {
      const date = getDateForIndex(col * DAYS_PER_WEEK);
      const month = date.getMonth();
      if (month !== lastMonth) {
        monthLabels.push({ col, label: date.toLocaleDateString(undefined, { month: 'short' }) });
        lastMonth = month;
      }
    }
    const workingSet = new Set(workingDays);
    const present = rawPresent.map((_, index) => {
      const date = getDateForIndex(index);
      if (!workingSet.has(date.getDay())) return false;
      return rawPresent[index];
    });
    const isOffDay = (index: number) => !workingSet.has(getDateForIndex(index).getDay());
    return { present, dayLabels, monthLabels, isOffDay };
  }, [agentId, workingDays]);

  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0 space-y-2">
      <div className="flex flex-1 min-h-0 min-w-0 gap-1">
        {/* Day-of-week labels (y-axis) */}
        <div className="flex flex-col justify-around text-[10px] text-text-muted pr-2 shrink-0">
          <span className="h-4 flex items-center opacity-0" aria-hidden>
            placeholder
          </span>
          {dayLabels.map((label) => (
            <span key={label} className="h-4 flex items-center">
              {label}
            </span>
          ))}
        </div>
        {/* Month row (x-axis) + grid - fills remaining space */}
        <div className="flex flex-col gap-0.5 flex-1 min-w-0 min-h-[100px]">
          {/* Month labels on x-axis */}
          <div className="flex gap-0.5 w-full">
            {Array.from({ length: WEEKS }, (_, col) => {
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
          {/* Grid: 26 columns (weeks), 7 rows (days) - equal width columns, one color when present */}
          <div className="flex gap-0.5 flex-1 min-w-0 w-full min-h-0">
            {Array.from({ length: WEEKS }, (_, col) => (
              <div key={col} className="flex flex-col gap-0.5 flex-1 min-w-0">
                {Array.from({ length: DAYS_PER_WEEK }, (_, row) => {
                  const index = col * DAYS_PER_WEEK + row;
                  const offDay = isOffDay(index);
                  const isPresent = !offDay && (present[index] ?? false);
                  const date = getDateForIndex(index);
                  const title = offDay
                    ? `${formatDate(date)} · Off day (holiday)`
                    : `${formatDate(date)} · ${isPresent ? 'Present' : 'Absent'}`;
                  return (
                    <div
                      key={row}
                      className={`${CELL_BASE} flex-1 min-h-2 min-w-0 cursor-default transition-colors ${
                        offDay
                          ? 'bg-[#ebedf0] opacity-70'
                          : isPresent
                            ? 'bg-primary hover:bg-primary/90'
                            : 'bg-[#ebedf0] hover:bg-[#e0e2e6]'
                      }`}
                      title={title}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
