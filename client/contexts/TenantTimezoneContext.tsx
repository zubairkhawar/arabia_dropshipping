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
const TZ_CACHE_KEY = 'tenant-display-timezone-v1';
const DEFAULT_TENANT_ID = 1;

type TenantTimezoneContextValue = {
  timeZone: string;
  /** Logged-in user's tenant; null when signed out or not yet loaded. */
  tenantId: number | null;
  setTimeZone: (tz: string) => void;
  refresh: () => Promise<void>;
};

const TenantTimezoneContext = createContext<TenantTimezoneContextValue | undefined>(undefined);

export function TenantTimezoneProvider({ children }: { children: ReactNode }) {
  const [timeZone, setTimeZoneState] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_TENANT_TIMEZONE;
    try {
      const cached = localStorage.getItem(TZ_CACHE_KEY);
      return normalizeIanaTimeZone(cached ?? DEFAULT_TENANT_TIMEZONE);
    } catch {
      return DEFAULT_TENANT_TIMEZONE;
    }
  });
  const [tenantId, setTenantIdState] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setTimeZoneState(DEFAULT_TENANT_TIMEZONE);
      setTenantIdState(null);
      return;
    }
    try {
      const meRes = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!meRes.ok) {
        return;
      }
      const me = (await meRes.json()) as {
        tenant_id?: number;
        tenant_display_timezone?: string;
      };
      const tid =
        typeof me.tenant_id === 'number' && Number.isFinite(me.tenant_id) ? me.tenant_id : null;
      setTenantIdState(tid);

      let tzSource: string | undefined = me.tenant_display_timezone;
      const tenantIdForTimezone = tid ?? DEFAULT_TENANT_ID;
      const tzRes = await fetch(`${API_BASE}/api/tenants/${tenantIdForTimezone}/display-timezone`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (tzRes.ok) {
        const body = (await tzRes.json()) as { display_timezone?: string };
        if (typeof body.display_timezone === 'string' && body.display_timezone.trim()) {
          tzSource = body.display_timezone.trim();
        }
      }

      const normalized = normalizeIanaTimeZone(tzSource);
      setTimeZoneState(normalized);
      try {
        localStorage.setItem(TZ_CACHE_KEY, normalized);
      } catch {
        // ignore cache write failure
      }
    } catch {
      // keep previous/cached value
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onAuthChanged = () => {
      void refresh();
    };
    if (typeof window !== 'undefined') {
      window.addEventListener('auth-changed', onAuthChanged);
    }
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('auth-changed', onAuthChanged);
      }
    };
  }, [refresh]);

  const setTimeZone = useCallback((tz: string) => {
    const normalized = normalizeIanaTimeZone(tz);
    setTimeZoneState(normalized);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(TZ_CACHE_KEY, normalized);
      }
    } catch {
      // ignore cache write failure
    }
  }, []);

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
