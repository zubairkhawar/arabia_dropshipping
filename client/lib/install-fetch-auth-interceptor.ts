import {
  API_BASE_URL,
  forceLoginRedirect,
  readStoredAuthToken,
} from '@/lib/auth-session';

let installed = false;

function parseRequestUrl(input: RequestInfo | URL): URL | null {
  try {
    if (typeof input === 'string') {
      return new URL(input, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    }
    if (input instanceof URL) return input;
    if (input instanceof Request) return new URL(input.url);
  } catch {
    return null;
  }
  return null;
}

function mergeRequestHeaders(input: RequestInfo | URL, init?: RequestInit): Headers {
  const merged = new Headers(init?.headers ?? undefined);
  if (input instanceof Request) {
    input.headers.forEach((value, key) => {
      if (!merged.has(key)) merged.set(key, value);
    });
  }
  return merged;
}

function hasBearerAuth(input: RequestInfo | URL, init?: RequestInit): boolean {
  const h = mergeRequestHeaders(input, init);
  const v = h.get('Authorization');
  return !!v && /^Bearer\s+\S+/i.test(v);
}

function isOurApiHost(host: string): boolean {
  try {
    return host === new URL(API_BASE_URL).host;
  } catch {
    return false;
  }
}

/** True when a 401 on this response should invalidate the browser session. */
function shouldSessionExpireOn401(
  status: number,
  requestUrl: URL | null,
  input: RequestInfo | URL,
  init?: RequestInit,
): boolean {
  if (status !== 401 || !requestUrl) return false;
  if (!isOurApiHost(requestUrl.host)) return false;

  const pathname = requestUrl.pathname;
  const publicAuth = /^\/api\/auth\/(login|register|forgot-password|reset-password|verify-reset-token)(?:\/|$)/;
  if (publicAuth.test(pathname)) return false;

  const hadBearer = hasBearerAuth(input, init);
  const hasStoredToken = !!readStoredAuthToken();
  return hadBearer || hasStoredToken;
}

/**
 * Wraps `window.fetch` once: on 401 from the configured API (except public auth routes),
 * clear auth and redirect to login when a session was present or Bearer was sent.
 */
export function installFetchAuthInterceptor(): void {
  if (typeof window === 'undefined' || installed) return;
  installed = true;

  const native = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await native(input, init);
    const url = parseRequestUrl(input);
    if (shouldSessionExpireOn401(response.status, url, input, init)) {
      forceLoginRedirect();
    }
    return response;
  };
}
