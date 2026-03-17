'use client';

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  ReactNode,
} from 'react';

const STORAGE_KEY = 'online-schedule';
const DEFAULT_TENANT_ID = 1;
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

/** 0 = Sunday, 1 = Monday, ... 6 = Saturday. Days not in this array are holidays (e.g. Sunday). */
export interface OnlineSchedule {
  workingDays: number[];
  startTime: string; // "09:00"
  endTime: string;   // "18:00"
}

const defaultSchedule: OnlineSchedule = {
  workingDays: [1, 2, 3, 4, 5, 6], // Mon–Sat; Sunday off
  startTime: '09:00',
  endTime: '18:00',
};

function loadSchedule(): OnlineSchedule {
  if (typeof window === 'undefined') return defaultSchedule;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultSchedule;
    const parsed = JSON.parse(raw) as Partial<OnlineSchedule>;
    return {
      workingDays: Array.isArray(parsed.workingDays) && parsed.workingDays.length > 0
        ? parsed.workingDays
        : defaultSchedule.workingDays,
      startTime: parsed.startTime ?? defaultSchedule.startTime,
      endTime: parsed.endTime ?? defaultSchedule.endTime,
    };
  } catch {
    return defaultSchedule;
  }
}

function saveSchedule(schedule: OnlineSchedule) {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(schedule));
    }
  } catch {
    // ignore
  }
}

function parseTime(s: string): { hours: number; minutes: number } {
  const [h, m] = s.split(':').map(Number);
  return { hours: h ?? 0, minutes: m ?? 0 };
}

/** Returns true if the given date falls within working days and hours. */
export function isWithinSchedule(schedule: OnlineSchedule, date: Date = new Date()): boolean {
  const day = date.getDay();
  if (!schedule.workingDays.includes(day)) return false;
  const start = parseTime(schedule.startTime);
  const end = parseTime(schedule.endTime);
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const currentMins = hours * 60 + minutes;
  const startMins = start.hours * 60 + start.minutes;
  const endMins = end.hours * 60 + end.minutes;
  return currentMins >= startMins && currentMins < endMins;
}

/** Returns true if the given day of week (0–6) is a working day. */
export function isWorkingDay(schedule: OnlineSchedule, dayOfWeek: number): boolean {
  return schedule.workingDays.includes(dayOfWeek);
}

interface OnlineScheduleContextType {
  schedule: OnlineSchedule;
  setSchedule: (schedule: OnlineSchedule) => void;
  isWithinSchedule: (date?: Date) => boolean;
  isWorkingDay: (dayOfWeek: number) => boolean;
}

const OnlineScheduleContext = createContext<OnlineScheduleContextType | undefined>(undefined);

export function OnlineScheduleProvider({ children }: { children: ReactNode }) {
  const [schedule, setScheduleState] = useState<OnlineSchedule>(defaultSchedule);

  useEffect(() => {
    // Load from local storage immediately for fast UI, then try backend override.
    setScheduleState(loadSchedule());

    async function fetchScheduleFromBackend() {
      try {
        const res = await fetch(`${API_BASE}/api/tenants/${DEFAULT_TENANT_ID}/schedule`);
        if (!res.ok) return;
        const data = (await res.json()) as { working_days: number[]; start_time: string; end_time: string };
        const next: OnlineSchedule = {
          workingDays: Array.isArray(data.working_days) && data.working_days.length > 0 ? data.working_days : defaultSchedule.workingDays,
          startTime: data.start_time || defaultSchedule.startTime,
          endTime: data.end_time || defaultSchedule.endTime,
        };
        setScheduleState(next);
        saveSchedule(next);
      } catch {
        // ignore, stay with local/default
      }
    }

    fetchScheduleFromBackend();
  }, []);

  const setSchedule = useCallback((next: OnlineSchedule) => {
    setScheduleState(next);
    saveSchedule(next);

    // Fire-and-forget sync to backend; errors are ignored on purpose.
    if (typeof window !== 'undefined') {
      fetch(`${API_BASE}/api/tenants/${DEFAULT_TENANT_ID}/schedule`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          working_days: next.workingDays,
          start_time: next.startTime,
          end_time: next.endTime,
        }),
      }).catch(() => undefined);
    }
  }, []);

  const isWithinScheduleNow = useCallback(
    (date?: Date) => isWithinSchedule(schedule, date ?? new Date()),
    [schedule],
  );

  const isWorkingDayCheck = useCallback(
    (dayOfWeek: number) => isWorkingDay(schedule, dayOfWeek),
    [schedule],
  );

  return (
    <OnlineScheduleContext.Provider
      value={{
        schedule,
        setSchedule,
        isWithinSchedule: isWithinScheduleNow,
        isWorkingDay: isWorkingDayCheck,
      }}
    >
      {children}
    </OnlineScheduleContext.Provider>
  );
}

export function useOnlineSchedule() {
  const context = useContext(OnlineScheduleContext);
  if (context === undefined) {
    return {
      schedule: defaultSchedule,
      setSchedule: () => {},
      isWithinSchedule: () => true,
      isWorkingDay: () => true,
    };
  }
  return context;
}
