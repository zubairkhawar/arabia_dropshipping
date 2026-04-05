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
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
          const u = parseUnread(msg);
          if (u) setUnread(u);
          notify(msg);
        } catch {
          // ignore
        }
      };
      ws.onclose = () => {
        wsRef.current = null;
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
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      try {
        wsRef.current?.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    };
  }, [notify, refreshUnread]);

  const value = useMemo(
    () => ({ unread, setUnread, subscribe, refreshUnread }),
    [unread, subscribe, refreshUnread],
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
    };
  }
  return ctx;
}
