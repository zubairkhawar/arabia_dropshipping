'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { DEFAULT_TENANT_TIMEZONE, normalizeIanaTimeZone } from '@/lib/tenant-time';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

type TenantTimezoneContextValue = {
  timeZone: string;
  setTimeZone: (tz: string) => void;
  refresh: () => Promise<void>;
};

const TenantTimezoneContext = createContext<TenantTimezoneContextValue | undefined>(undefined);

export function TenantTimezoneProvider({ children }: { children: ReactNode }) {
  const [timeZone, setTimeZoneState] = useState(DEFAULT_TENANT_TIMEZONE);

  const refresh = useCallback(async () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setTimeZoneState(DEFAULT_TENANT_TIMEZONE);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = (await res.json()) as { tenant_display_timezone?: string };
      setTimeZoneState(normalizeIanaTimeZone(data.tenant_display_timezone));
    } catch {
      // keep previous
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setTimeZone = useCallback((tz: string) => {
    setTimeZoneState(normalizeIanaTimeZone(tz));
  }, []);

  const value = useMemo(
    () => ({ timeZone, setTimeZone, refresh }),
    [timeZone, setTimeZone, refresh],
  );

  return (
    <TenantTimezoneContext.Provider value={value}>{children}</TenantTimezoneContext.Provider>
  );
}

export function useTenantTimezone(): TenantTimezoneContextValue {
  const ctx = useContext(TenantTimezoneContext);
  if (!ctx) {
    return {
      timeZone: DEFAULT_TENANT_TIMEZONE,
      setTimeZone: () => {},
      refresh: async () => {},
    };
  }
  return ctx;
}
