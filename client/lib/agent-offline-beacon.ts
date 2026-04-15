import { AGENT_PORTAL_PREFERS_OFFLINE_KEY, readAuthAgentId } from '@/lib/agent-session-storage';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

/**
 * Marks the current agent offline using a keepalive request so it still runs when the tab closes.
 */
export function sendAgentOfflineKeepalive(): void {
  if (typeof window === 'undefined') return;
  try {
    const id = readAuthAgentId();
    const token = localStorage.getItem('auth_token');
    const role = (localStorage.getItem('auth_role') || '').toLowerCase();
    if (!id || !token || role !== 'agent') return;
    const numericId = Number(id);
    if (!Number.isFinite(numericId) || numericId < 1) return;
    void fetch(`${API_BASE}/api/routing/agents/${numericId}/status`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ status: 'offline' }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // ignore
  }
}
