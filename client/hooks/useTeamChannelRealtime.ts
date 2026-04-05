'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

export interface TeamReceiptSummaryPayload {
  recipient_count: number;
  delivered_count: number;
  read_count: number;
}

export interface TeamChannelWsMessage {
  id: number;
  team_id: number;
  sender_agent_id: number | null;
  posted_by_admin?: boolean;
  sender_name: string;
  content: string;
  created_at: string;
  reply_to_message_id?: number | null;
  edited_at?: string | null;
  deleted_for_everyone_at?: string | null;
  receipt_summary?: TeamReceiptSummaryPayload | null;
}

export type TeamChannelWsEvent =
  | { type: 'NEW_MESSAGE'; message: TeamChannelWsMessage }
  | { type: 'MESSAGE_UPDATED'; message: TeamChannelWsMessage }
  | { type: 'TYPING'; team_id: number; agent_id: number | null; name: string; active: boolean }
  | { type: 'READ_STATE'; agent_id: number; last_read_message_id: number }
  | {
      type: 'RECEIPTS_UPDATED';
      team_id: number;
      summaries: Array<
        TeamReceiptSummaryPayload & {
          message_id: number;
        }
      >;
    };

function wsUrlForTeamChannel(teamId: number, tenantId: number, token: string): string {
  const wsBase = API_BASE.replace(/^http/i, (m) => (m.toLowerCase() === 'https' ? 'wss' : 'ws'));
  const q = new URLSearchParams({
    tenant_id: String(tenantId),
    token,
  });
  return `${wsBase}/api/teams/ws/channel/${teamId}?${q.toString()}`;
}

export type TeamChannelRealtimeOptions = {
  onOpen?: () => void;
  onClose?: () => void;
};

export type TeamChannelRealtimeControls = {
  sendTyping: (active: boolean) => void;
  sendDeliveryAck: (messageIds: number[]) => void;
};

/**
 * Subscribes to team channel WebSocket when enabled. Typing + delivery ack outbound.
 */
export function useTeamChannelRealtime(
  enabled: boolean,
  teamId: number | null,
  tenantId: number,
  onEvent: (event: TeamChannelWsEvent) => void,
  options?: TeamChannelRealtimeOptions,
): TeamChannelRealtimeControls {
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

  const sendTyping = useCallback((active: boolean) => {
    const s = wsRef.current;
    if (!s || s.readyState !== WebSocket.OPEN) return;
    try {
      s.send(JSON.stringify({ type: 'typing', active }));
    } catch {
      // ignore
    }
  }, []);

  const sendDeliveryAck = useCallback((messageIds: number[]) => {
    const s = wsRef.current;
    if (!s || s.readyState !== WebSocket.OPEN || messageIds.length === 0) return;
    try {
      s.send(JSON.stringify({ type: 'delivery_ack', message_ids: messageIds }));
    } catch {
      // ignore
    }
  }, []);

  return useMemo(
    () => ({ sendTyping, sendDeliveryAck }),
    [sendTyping, sendDeliveryAck],
  );
}
