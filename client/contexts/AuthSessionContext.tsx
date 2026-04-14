'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  API_BASE_URL,
  clearAuthSession,
  forceLoginRedirect,
  isProtectedWorkspaceRoute,
  isPublicAppRoute,
  isStoredTokenExpired,
  readStoredAuthToken,
} from '@/lib/auth-session';
import { installFetchAuthInterceptor } from '@/lib/install-fetch-auth-interceptor';

type AuthSessionContextValue = {
  /** Clears tokens and agent id; dispatches `auth-changed`. Does not navigate. */
  clearSession: () => void;
  /** Validates JWT with `/api/auth/me` when a token exists on protected routes. */
  validateSession: () => Promise<void>;
};

const AuthSessionContext = createContext<AuthSessionContextValue | undefined>(undefined);

/** `invalid` = 401 from server (session cleared + redirect). `unknown` = network/5xx — do not redirect. */
async function validateTokenWithServer(token: string): Promise<'ok' | 'invalid' | 'unknown'> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 401) {
      forceLoginRedirect();
      return 'invalid';
    }
    if (res.ok) return 'ok';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const clearSession = useCallback(() => {
    clearAuthSession();
  }, []);

  const validateSession = useCallback(async () => {
    if (typeof window === 'undefined') return;
    if (isPublicAppRoute(pathname)) return;
    if (!isProtectedWorkspaceRoute(pathname)) return;

    const token = readStoredAuthToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    if (isStoredTokenExpired()) {
      forceLoginRedirect();
      return;
    }

    const v = await validateTokenWithServer(token);
    if (v === 'invalid') return;
    if (v !== 'ok') return;
  }, [pathname, router]);

  useEffect(() => {
    installFetchAuthInterceptor();
  }, []);

  useEffect(() => {
    void validateSession();
  }, [validateSession]);

  useEffect(() => {
    const onFocus = () => {
      if (!isProtectedWorkspaceRoute(pathname)) return;
      if (!readStoredAuthToken()) return;
      if (isStoredTokenExpired()) {
        forceLoginRedirect();
      }
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [pathname]);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (!isProtectedWorkspaceRoute(pathname)) return;
      if (!readStoredAuthToken()) return;
      if (isStoredTokenExpired()) {
        forceLoginRedirect();
      }
    }, 45_000);
    return () => window.clearInterval(id);
  }, [pathname]);

  const value = useMemo(
    () => ({
      clearSession,
      validateSession,
    }),
    [clearSession, validateSession],
  );

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession(): AuthSessionContextValue {
  const ctx = useContext(AuthSessionContext);
  if (!ctx) {
    throw new Error('useAuthSession must be used within AuthSessionProvider');
  }
  return ctx;
}
