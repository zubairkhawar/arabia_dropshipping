'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  ReactNode,
} from 'react';

import { useAgents } from '@/contexts/AgentsContext';
import {
  AGENT_PORTAL_IDLE_OFFLINE_KEY,
  AGENT_PORTAL_PREFERS_OFFLINE_KEY,
  readAuthAgentId,
} from '@/lib/agent-session-storage';
import { sendAgentOfflineKeepalive } from '@/lib/agent-offline-beacon';
import { redirectIfWebSocketAuthFailure } from '@/lib/auth-session';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

export type AgentPortalUnread = {
  inbox: number;
  team_channel: number;
  dm: number;
};

type PortalListener = (msg: Record<string, unknown>) => void;

type AgentPortalRealtimeContextType = {
  unread: AgentPortalUnread;
  setUnread: React.Dispatch<React.SetStateAction<AgentPortalUnread>>;
  subscribe: (fn: PortalListener) => () => void;
  refreshUnread: () => Promise<void>;
  sendToPortal: (payload: Record<string, unknown>) => void;
};

const defaultUnread: AgentPortalUnread = { inbox: 0, team_channel: 0, dm: 0 };

const AgentPortalRealtimeContext = createContext<AgentPortalRealtimeContextType | null>(null);

function parseUnread(msg: Record<string, unknown>): AgentPortalUnread | null {
  const inbox = msg.inbox;
  const team = msg.team_channel;
  const dm = msg.dm;
  if (
    typeof inbox === 'number' &&
    typeof team === 'number' &&
    typeof dm === 'number'
  ) {
    return { inbox, team_channel: team, dm };
  }
  return null;
}

export function AgentPortalRealtimeProvider({ children }: { children: ReactNode }) {
  const { setAgentStatus, getCurrentAgent } = useAgents();
  const [unread, setUnread] = useState<AgentPortalUnread>(defaultUnread);
  const listenersRef = useRef(new Set<PortalListener>());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const subscribe = useCallback((fn: PortalListener) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  const notify = useCallback((msg: Record<string, unknown>) => {
    listenersRef.current.forEach((fn) => {
      try {
        fn(msg);
      } catch {
        // ignore listener errors
      }
    });
  }, []);

  const sendToPortal = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify(payload));
    } catch {
      // ignore
    }
  }, []);

  const refreshUnread = useCallback(async () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    const role = (localStorage.getItem('auth_role') || '').toLowerCase();
    if (!token || role !== 'agent') return;
    try {
      const url = new URL(`${API_BASE}/api/agent-portal/unread-summary`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) return;
      const data = (await res.json()) as AgentPortalUnread;
      if (
        typeof data.inbox === 'number' &&
        typeof data.team_channel === 'number' &&
        typeof data.dm === 'number'
      ) {
        setUnread(data);
      }
    } catch {
      // ignore
    }
  }, []);

  // Heartbeat: ping the server every 30 minutes while the tab is visible and the
  // agent is online. This ensures open attendance sessions stay alive and a missing
  // session (accidentally closed) gets recreated automatically.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    const role = (localStorage.getItem('auth_role') || '').toLowerCase();
    if (!token || role !== 'agent') return;

    const sendHeartbeat = () => {
      if (document.visibilityState !== 'visible') return;
      if (sessionStorage.getItem(AGENT_PORTAL_PREFERS_OFFLINE_KEY) === '1') return;
      if (sessionStorage.getItem(AGENT_PORTAL_IDLE_OFFLINE_KEY) === '1') return;
      const id = readAuthAgentId();
      if (!id) return;
      void fetch(`${API_BASE}/api/routing/agents/${id}/heartbeat`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => undefined);
    };

    // Fire once after a short delay (page load / reconnect), then every 30 minutes.
    const initialTimer = window.setTimeout(sendHeartbeat, 5000);
    const intervalTimer = window.setInterval(sendHeartbeat, 30 * 60 * 1000);

    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(intervalTimer);
    };
  }, []);

  // Auto-offline after inactivity (visible tab) or a long backgrounded tab, so attendance
  // does not stay "online" when the agent has walked away.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    const role = (localStorage.getItem('auth_role') || '').toLowerCase();
    if (!token || role !== 'agent') return;

    const INACTIVITY_MS = 15 * 60 * 1000;
    const HIDDEN_MS = 30 * 60 * 1000;
    const lastActivityRef = { current: Date.now() };
    let hiddenSince: number | null = null;

    const bump = () => {
      lastActivityRef.current = Date.now();
    };
    const passive = { passive: true } as AddEventListenerOptions;
    window.addEventListener('pointerdown', bump, passive);
    window.addEventListener('keydown', bump);
    window.addEventListener('wheel', bump, passive);

    const onVis = () => {
      if (document.visibilityState === 'hidden') {
        hiddenSince = Date.now();
      } else {
        hiddenSince = null;
        lastActivityRef.current = Date.now();
      }
    };
    document.addEventListener('visibilitychange', onVis);

    const maybeIdleOffline = () => {
      if (sessionStorage.getItem(AGENT_PORTAL_PREFERS_OFFLINE_KEY) === '1') return;
      const id = readAuthAgentId();
      if (!id) return;
      const me = getCurrentAgent();
      if (!me || (me.status !== 'online' && me.status !== 'busy')) return;

      const now = Date.now();
      if (document.visibilityState === 'hidden' && hiddenSince != null && now - hiddenSince >= HIDDEN_MS) {
        sessionStorage.setItem(AGENT_PORTAL_IDLE_OFFLINE_KEY, '1');
        void setAgentStatus(id, 'offline');
        hiddenSince = null;
        return;
      }
      if (document.visibilityState === 'visible' && now - lastActivityRef.current >= INACTIVITY_MS) {
        sessionStorage.setItem(AGENT_PORTAL_IDLE_OFFLINE_KEY, '1');
        void setAgentStatus(id, 'offline');
      }
    };

    const intervalTimer = window.setInterval(maybeIdleOffline, 30_000);
    return () => {
      window.clearInterval(intervalTimer);
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('pointerdown', bump);
      window.removeEventListener('keydown', bump);
      window.removeEventListener('wheel', bump);
    };
  }, [getCurrentAgent, setAgentStatus]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    const role = (localStorage.getItem('auth_role') || '').toLowerCase();
    if (!token || role !== 'agent') return;

    void refreshUnread();

    const baseWs = API_BASE.replace(/^http/, 'ws');
    const connect = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const url = new URL(`${baseWs}/api/agent-portal/ws`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('token', token);
      let ws: WebSocket;
      try {
        ws = new WebSocket(url.toString());
      } catch {
        reconnectTimerRef.current = setTimeout(connect, 4000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        if (typeof window === 'undefined') return;
        const sync = () => {
          if (sessionStorage.getItem(AGENT_PORTAL_PREFERS_OFFLINE_KEY) === '1') return;
          if (sessionStorage.getItem(AGENT_PORTAL_IDLE_OFFLINE_KEY) === '1') return;
          const id = readAuthAgentId();
          if (id) void setAgentStatus(id, 'online');
        };
        // Let downstream contexts recover any missed events during reconnect gaps.
        notify({ type: 'portal_connected' });
        sync();
        window.setTimeout(sync, 500);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
          const u = parseUnread(msg);
          if (u) setUnread(u);
          if (msg.type === 'inbox_message' && msg.message && typeof msg.message === 'object') {
            const mid = (msg.message as Record<string, unknown>).id;
            if (typeof mid === 'number') {
              try {
                ws.send(
                  JSON.stringify({ type: 'delivery_ack', channel: 'inbox', message_ids: [mid] }),
                );
              } catch {
                // ignore
              }
            }
          }
          notify(msg);
        } catch {
          // ignore
        }
      };
      ws.onclose = (ev) => {
        wsRef.current = null;
        if (redirectIfWebSocketAuthFailure(ev)) {
          return;
        }
        reconnectTimerRef.current = setTimeout(connect, 4000);
      };
      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          // ignore
        }
      };
    };

    connect();

    const onPageHide = (ev: PageTransitionEvent) => {
      if (ev.persisted) return;
      sendAgentOfflineKeepalive();
    };
    window.addEventListener('pagehide', onPageHide);

    return () => {
      window.removeEventListener('pagehide', onPageHide);
      sendAgentOfflineKeepalive();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      try {
        wsRef.current?.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    };
  }, [notify, refreshUnread, setAgentStatus]);

  const value = useMemo(
    () => ({ unread, setUnread, subscribe, refreshUnread, sendToPortal }),
    [unread, subscribe, refreshUnread, sendToPortal],
  );

  return (
    <AgentPortalRealtimeContext.Provider value={value}>{children}</AgentPortalRealtimeContext.Provider>
  );
}

export function useAgentPortalRealtime() {
  const ctx = useContext(AgentPortalRealtimeContext);
  if (!ctx) {
    return {
      unread: defaultUnread,
      setUnread: (_: React.SetStateAction<AgentPortalUnread>) => {},
      subscribe: (_fn: PortalListener) => () => {},
      refreshUnread: async () => {},
      sendToPortal: (_: Record<string, unknown>) => {},
    };
  }
  return ctx;
}
