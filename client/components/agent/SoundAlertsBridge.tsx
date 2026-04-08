'use client';

import { useEffect } from 'react';
import { useAgentPortalRealtime } from '@/contexts/AgentPortalRealtimeContext';
import { notificationTypeToSound, useSoundAlerts } from '@/contexts/SoundAlertsContext';

/**
 * Subscribes to agent portal WebSocket: plays debounced sounds for push notifications
 * and inbound customer inbox messages.
 */
export function SoundAlertsBridge() {
  const { subscribe } = useAgentPortalRealtime();
  const { requestPlay } = useSoundAlerts();

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'notification' && msg.notification && typeof msg.notification === 'object') {
        const raw = msg.notification as Record<string, unknown>;
        const t = String(raw.type ?? 'system');
        requestPlay(notificationTypeToSound(t));
        return;
      }
      if (msg.type === 'inbox_message' && msg.message && typeof msg.message === 'object') {
        const m = msg.message as Record<string, unknown>;
        if (String(m.sender_type ?? '') === 'customer') {
          requestPlay('customer_message');
        }
      }
    });
  }, [subscribe, requestPlay]);

  return null;
}
