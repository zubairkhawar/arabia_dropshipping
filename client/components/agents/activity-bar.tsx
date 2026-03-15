'use client';

import { useMemo, useState } from 'react';

const WEEKS = 26;
const DAYS_PER_WEEK = 7;
const TOTAL_DAYS = WEEKS * DAYS_PER_WEEK;

const CELL_CLASS = 'w-3 h-3 rounded-sm shrink-0';

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

export function AgentActivityBar({ agentId }: { agentId: string }) {
  const [tooltip, setTooltip] = useState<{ date: string; present: boolean } | null>(null);

  const { present, dayLabels, monthLabels } = useMemo(() => {
    const present = getAttendancePresent(agentId);
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
    return { present, dayLabels, monthLabels };
  }, [agentId]);

  return (
    <div className="space-y-2">
      <div className="flex gap-1 overflow-x-auto pb-1">
        {/* Day-of-week labels (y-axis) */}
        <div className="flex flex-col justify-around text-[10px] text-text-muted pr-1 shrink-0">
          <span className="h-3 flex items-center opacity-0" aria-hidden>
            placeholder
          </span>
          {dayLabels.map((label) => (
            <span key={label} className="h-3 flex items-center">
              {label}
            </span>
          ))}
        </div>
        {/* Month row (x-axis) + grid */}
        <div className="flex flex-col gap-0.5 min-w-0">
          {/* Month labels on x-axis */}
          <div className="flex gap-0.5">
            {Array.from({ length: WEEKS }, (_, col) => {
              const label = monthLabels.find((m) => m.col === col);
              return (
                <div
                  key={col}
                  className={`${CELL_CLASS} flex items-center justify-center text-[9px] text-text-muted font-medium`}
                >
                  {label?.label ?? ''}
                </div>
              );
            })}
          </div>
          {/* Grid: 26 columns (weeks), 7 rows (days) - one color when present */}
          <div className="flex gap-0.5">
            {Array.from({ length: WEEKS }, (_, col) => (
              <div key={col} className="flex flex-col gap-0.5">
                {Array.from({ length: DAYS_PER_WEEK }, (_, row) => {
                  const index = col * DAYS_PER_WEEK + row;
                  const isPresent = present[index] ?? false;
                  const date = getDateForIndex(index);
                  return (
                    <div
                      key={row}
                      className={`${CELL_CLASS} cursor-default transition-colors ${
                        isPresent
                          ? 'bg-primary hover:bg-primary/90'
                          : 'bg-[#ebedf0] hover:bg-[#e0e2e6]'
                      }`}
                      title={formatDate(date)}
                      onMouseEnter={() => setTooltip({ date: formatDate(date), present: isPresent })}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
      {tooltip && (
        <p className="text-xs text-text-muted">
          {tooltip.date} · {tooltip.present ? 'Present' : 'Absent'}
        </p>
      )}
    </div>
  );
}
