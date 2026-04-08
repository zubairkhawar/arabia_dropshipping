'use client';

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { DEFAULT_TENANT_TIMEZONE } from '@/lib/tenant-time';

type TenantTimezoneContextValue = {
  timeZone: string;
  /** Logged-in user's tenant; null when signed out or not yet loaded. */
  tenantId: number | null;
  setTimeZone: (tz: string) => void;
  refresh: () => Promise<void>;
};

const TenantTimezoneContext = createContext<TenantTimezoneContextValue | undefined>(undefined);

export function TenantTimezoneProvider({ children }: { children: ReactNode }) {
  const [timeZone] = useState(DEFAULT_TENANT_TIMEZONE);
  const [tenantId] = useState<number | null>(1);

  const setTimeZone = (_tz: string) => {};
  const refresh = async () => {};

  const value = useMemo(
    () => ({ timeZone, tenantId, setTimeZone, refresh }),
    [timeZone, tenantId, setTimeZone, refresh],
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
      tenantId: null,
      setTimeZone: () => {},
      refresh: async () => {},
    };
  }
  return ctx;
}
