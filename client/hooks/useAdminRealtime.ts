'use client';

import { useEffect, useRef } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

export type AdminRealtimeEvent =
  | {
      type: 'template_status_update';
      template_id: number;
      name: string;
      language: string;
      status: string;
      rejection_reason: string | null;
      meta_template_id: string | null;
    }
  | { type: 'template_deleted'; template_id: number }
  | {
      type: 'campaign_status_update';
      campaign_id: number;
      status: string;
      sent_count: number;
      failed_count: number;
      recipient_count: number;
    }
  | {
      type: 'recipient_status_update';
      campaign_id: number;
      recipient_id: number;
      phone: string;
      status: string;
      error_message: string | null;
    }
  | { type: 'ready'; tenant_id: number };

function buildWsUrl(tenantId: number, token: string): string {
  const httpBase = API_BASE.replace(/^http/, 'ws');
  const url = new URL(`${httpBase}/api/admin-realtime/ws`);
  url.searchParams.set('tenant_id', String(tenantId));
  url.searchParams.set('token', token);
  return url.toString();
}

/**
 * Single admin WebSocket. Reconnects on close with a 4s backoff.
 * No polling — every status update comes through here.
 */
export function useAdminRealtime(
  tenantId: number | null,
  onEvent: (ev: AdminRealtimeEvent) => void,
): void {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!tenantId || typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) return;

    let ws: WebSocket | null = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      if (cancelled) return;
      try {
        ws = new WebSocket(buildWsUrl(tenantId, token));
      } catch {
        scheduleReconnect();
        return;
      }
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as AdminRealtimeEvent;
          handlerRef.current(parsed);
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (!cancelled) scheduleReconnect();
      };
      ws.onerror = () => {
        ws?.close();
      };
    };

    const scheduleReconnect = () => {
      if (reconnectTimer || cancelled) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        open();
      }, 4000);
    };

    open();
    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [tenantId]);
}
