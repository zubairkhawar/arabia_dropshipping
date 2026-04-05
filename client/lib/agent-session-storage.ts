/** Persisted agent session hints for fast cold start and restoring the last-open thread. */

export const AUTH_AGENT_ID_KEY = 'auth_agent_id';
export const LAST_INBOX_CONVERSATION_ID_KEY = 'agent_last_inbox_conversation_id';
export const LAST_DM_CONVERSATION_ID_KEY = 'agent_last_dm_conversation_id';
export const LAST_DM_SLUG_KEY = 'agent_last_dm_slug';

export function readAuthAgentId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(AUTH_AGENT_ID_KEY);
  } catch {
    return null;
  }
}

export function writeAuthAgentId(agentId: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AUTH_AGENT_ID_KEY, agentId);
  } catch {
    // ignore
  }
}

export function clearAuthAgentId(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(AUTH_AGENT_ID_KEY);
  } catch {
    // ignore
  }
}

export function readLastInboxConversationId(): number | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(LAST_INBOX_CONVERSATION_ID_KEY);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

export function writeLastInboxConversationId(id: number): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LAST_INBOX_CONVERSATION_ID_KEY, String(id));
  } catch {
    // ignore
  }
}

export function readLastDmPrefs(): { conversationId: string; slug: string } | null {
  if (typeof window === 'undefined') return null;
  try {
    const id = localStorage.getItem(LAST_DM_CONVERSATION_ID_KEY);
    const slug = localStorage.getItem(LAST_DM_SLUG_KEY);
    if (!id || !slug) return null;
    return { conversationId: id, slug };
  } catch {
    return null;
  }
}

export function writeLastDmPrefs(conversationId: string, slug: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LAST_DM_CONVERSATION_ID_KEY, conversationId);
    localStorage.setItem(LAST_DM_SLUG_KEY, slug);
  } catch {
    // ignore
  }
}
