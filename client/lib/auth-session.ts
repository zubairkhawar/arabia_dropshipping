import { clearAuthAgentId } from '@/lib/agent-session-storage';

const AUTH_STORAGE_KEYS = ['auth_token', 'auth_token_type', 'auth_email', 'auth_role'] as const;

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

/** Routes where we never hard-redirect away (user is not in a protected shell). */
export function isPublicAppRoute(pathname: string): boolean {
  if (pathname === '/login') return true;
  if (pathname.startsWith('/forgot-password')) return true;
  if (pathname.startsWith('/reset-password')) return true;
  if (pathname === '/privacy-policy') return true;
  return false;
}

/** Workspace areas that require a valid session. */
export function isProtectedWorkspaceRoute(pathname: string): boolean {
  return pathname.startsWith('/admin') || pathname.startsWith('/agent');
}

export function clearAuthSession(): void {
  if (typeof window === 'undefined') return;
  try {
    for (const k of AUTH_STORAGE_KEYS) {
      localStorage.removeItem(k);
    }
    clearAuthAgentId();
    window.dispatchEvent(new Event('auth-changed'));
  } catch {
    // ignore storage errors
  }
}

/**
 * Clears session and sends the browser to /login (unless already on a public auth route).
 * Uses location.replace so back button does not return to a broken protected page.
 */
export function forceLoginRedirect(): void {
  if (typeof window === 'undefined') return;
  if (isPublicAppRoute(window.location.pathname)) return;
  clearAuthSession();
  window.location.replace('/login');
}

/**
 * WebSocket close codes / reasons that mean the token is invalid — redirect to login
 * instead of reconnecting forever with a dead session.
 */
export function redirectIfWebSocketAuthFailure(ev: CloseEvent): boolean {
  if (typeof window === 'undefined') return false;
  const code = ev.code;
  const reason = String(ev.reason || '').toLowerCase();
  if (code === 4001 || code === 4401 || code === 4403) {
    forceLoginRedirect();
    return true;
  }
  if (
    code === 1008 &&
    (reason.includes('auth') ||
      reason.includes('token') ||
      reason.includes('jwt') ||
      reason.includes('unauthorized') ||
      reason.includes('forbidden'))
  ) {
    forceLoginRedirect();
    return true;
  }
  return false;
}

export function readStoredAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem('auth_token');
  } catch {
    return null;
  }
}

/** JWT `exp` claim as Unix ms, or null if missing / not a JWT. */
export function readJwtExpiryMs(token: string): number | null {
  const parts = token.split('.');
  if (parts.length < 2) return null;
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const json = JSON.parse(atob(padded)) as { exp?: number };
    if (typeof json.exp !== 'number') return null;
    return json.exp * 1000;
  } catch {
    return null;
  }
}

export function isStoredTokenExpired(): boolean {
  const t = readStoredAuthToken();
  if (!t) return false;
  const exp = readJwtExpiryMs(t);
  if (exp == null) return false;
  return Date.now() >= exp;
}
