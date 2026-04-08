'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { playAgentSound, type AgentSoundKind } from '@/lib/agent-sounds';

const STORAGE_KEY = 'arabia-sound-alerts-v1';

/** Minimum gap between any two sounds (debounce / anti-spam). */
export const SOUND_DEBOUNCE_MS = 3000;

export type SoundAlertsState = {
  /** Master: play sounds for new messages / notifications */
  enabled: boolean;
};

const defaultState: SoundAlertsState = {
  enabled: true,
};

function loadState(): SoundAlertsState {
  if (typeof window === 'undefined') return defaultState;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    const o = JSON.parse(raw) as Partial<SoundAlertsState>;
    return {
      enabled: typeof o.enabled === 'boolean' ? o.enabled : defaultState.enabled,
    };
  } catch {
    return defaultState;
  }
}

function saveState(s: SoundAlertsState) {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    }
  } catch {
    // ignore
  }
}

export function notificationTypeToSound(type: string): AgentSoundKind {
  switch (type) {
    case 'mention':
      return 'mention';
    case 'chat_transfer':
      return 'escalation';
    case 'assignment':
    case 'team_assigned':
      return 'assignment';
    case 'personal_message':
      return 'new_dm';
    case 'new_message':
    case 'new_lead':
    case 'bot_new_chat':
    case 'broadcast':
    case 'team_removed':
    case 'team_changed':
    case 'system_welcome':
    case 'system':
    default:
      return 'customer_message';
  }
}

type SoundAlertsContextValue = {
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  /** Respects master toggle and 3s debounce across all kinds. */
  requestPlay: (kind: AgentSoundKind) => void;
};

const SoundAlertsContext = createContext<SoundAlertsContextValue | undefined>(undefined);

export function SoundAlertsProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabledState] = useState(defaultState.enabled);
  const lastPlayRef = useRef(0);

  useEffect(() => {
    setEnabledState(loadState().enabled);
  }, []);

  const setEnabled = useCallback((v: boolean) => {
    setEnabledState(v);
    saveState({ enabled: v });
  }, []);

  const requestPlay = useCallback(
    (kind: AgentSoundKind) => {
      if (!enabled) return;
      const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
      const last = lastPlayRef.current;
      if (now - last < SOUND_DEBOUNCE_MS) return;
      lastPlayRef.current = now;
      try {
        playAgentSound(kind);
      } catch {
        // ignore audio failures
      }
    },
    [enabled],
  );

  const value = useMemo(
    () => ({ enabled, setEnabled, requestPlay }),
    [enabled, setEnabled, requestPlay],
  );

  return <SoundAlertsContext.Provider value={value}>{children}</SoundAlertsContext.Provider>;
}

export function useSoundAlerts(): SoundAlertsContextValue {
  const ctx = useContext(SoundAlertsContext);
  if (!ctx) {
    return {
      enabled: false,
      setEnabled: () => {},
      requestPlay: () => {},
    };
  }
  return ctx;
}
