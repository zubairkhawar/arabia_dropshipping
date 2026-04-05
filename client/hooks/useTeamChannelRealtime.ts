'use client';

import { useCallback, useEffect, useRef } from 'react';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

export interface TeamChannelWsMessage {
  id: number;
  team_id: number;
  sender_agent_id: number | null;
  posted_by_admin?: boolean;
  sender_name: string;
  content: string;
  created_at: string;
}

export type TeamChannelWsEvent =
  | { type: 'NEW_MESSAGE'; message: TeamChannelWsMessage }
  | { type: 'MESSAGE_UPDATED'; message: TeamChannelWsMessage }
  | { type: 'TYPING'; team_id: number; agent_id: number | null; name: string; active: boolean }
  | { type: 'READ_STATE'; agent_id: number; last_read_message_id: number };

function wsUrlForTeamChannel(teamId: number, tenantId: number, token: string): string {
  const wsBase = API_BASE.replace(/^http/i, (m) => (m.toLowerCase() === 'https' ? 'wss' : 'ws'));
  const q = new URLSearchParams({
    tenant_id: String(tenantId),
    token,
  });
  return `${wsBase}/api/teams/ws/channel/${teamId}?${q.toString()}`;
}

/**
 * Subscribes to team channel WebSocket when enabled. Returns sendTyping(active) for debounced typing signals.
 */
export type TeamChannelRealtimeOptions = {
  onOpen?: () => void;
  onClose?: () => void;
};

export function useTeamChannelRealtime(
  enabled: boolean,
  teamId: number | null,
  tenantId: number,
  onEvent: (event: TeamChannelWsEvent) => void,
  options?: TeamChannelRealtimeOptions,
): (active: boolean) => void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled || teamId == null || teamId < 1) {
      wsRef.current = null;
      return;
    }
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrlForTeamChannel(teamId, tenantId, token));
        wsRef.current = ws;
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        optionsRef.current?.onOpen?.();
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as TeamChannelWsEvent;
          if (data && typeof data === 'object' && 'type' in data) {
            onEventRef.current(data);
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        optionsRef.current?.onClose?.();
        if (!closed) scheduleReconnect();
      };

      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          // ignore
        }
        wsRef.current = null;
      };
    };

    const scheduleReconnect = () => {
      if (closed) return;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 4000);
    };

    connect();

    return () => {
      closed = true;
      wsRef.current = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, [enabled, teamId, tenantId]);

  return useCallback((active: boolean) => {
    const s = wsRef.current;
    if (!s || s.readyState !== WebSocket.OPEN) return;
    try {
      s.send(JSON.stringify({ type: 'typing', active }));
    } catch {
      // ignore
    }
  }, []);
}
