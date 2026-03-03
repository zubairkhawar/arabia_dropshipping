'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgentProfile } from '@/contexts/AgentProfileContext';

const STORAGE_KEY = 'agent-presence';

export type PresenceStatus = 'active' | 'offline';

/** Agents grouped by team for DM picker. Slug is used in routes and presence. */
export const AGENTS_BY_TEAM: { team: string; members: { slug: string; name: string }[] }[] = [
  { team: 'Team A', members: [{ slug: 'hamza', name: 'Hamza' }, { slug: 'zubair', name: 'Zubair' }] },
  { team: 'Team B', members: [{ slug: 'ali', name: 'Ali' }, { slug: 'alina', name: 'Alina' }] },
  { team: 'Team C', members: [{ slug: 'aizal', name: 'Aizal' }, { slug: 'waqar', name: 'Waqar' }] },
];

export function getSlugByName(name: string): string | null {
  const normalized = name.trim().toLowerCase();
  for (const { members } of AGENTS_BY_TEAM) {
    const m = members.find((x) => x.name.toLowerCase() === normalized);
    if (m) return m.slug;
  }
  return null;
}

function loadPresenceFromStorage(): Record<string, PresenceStatus> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function savePresenceToStorage(map: Record<string, PresenceStatus>) {
  try {
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

interface AgentPresenceContextType {
  getPresence: (slug: string) => PresenceStatus;
  setPresence: (slug: string, status: PresenceStatus) => void;
  agentsByTeam: typeof AGENTS_BY_TEAM;
}

const AgentPresenceContext = createContext<AgentPresenceContextType | undefined>(undefined);

export function AgentPresenceProvider({ children }: { children: ReactNode }) {
  const { fullName } = useAgentProfile();
  const [presenceMap, setPresenceMap] = useState<Record<string, PresenceStatus>>(loadPresenceFromStorage);

  useEffect(() => {
    setPresenceMap(loadPresenceFromStorage());
  }, []);

  const setPresence = useCallback((slug: string, status: PresenceStatus) => {
    setPresenceMap((prev) => {
      const next = { ...prev, [slug]: status };
      savePresenceToStorage(next);
      return next;
    });
  }, []);

  const getPresence = useCallback(
    (slug: string): PresenceStatus => presenceMap[slug] ?? 'offline',
    [presenceMap],
  );

  // When current agent (fullName) is in our agents list, mark them active. On unmount or change, set offline.
  useEffect(() => {
    const slug = getSlugByName(fullName);
    if (slug) setPresence(slug, 'active');
    return () => {
      if (slug) setPresence(slug, 'offline');
    };
  }, [fullName, setPresence]);

  return (
    <AgentPresenceContext.Provider
      value={{
        getPresence,
        setPresence,
        agentsByTeam: AGENTS_BY_TEAM,
      }}
    >
      {children}
    </AgentPresenceContext.Provider>
  );
}

export function useAgentPresence() {
  const context = useContext(AgentPresenceContext);
  if (context === undefined) {
    return {
      getPresence: (_slug: string) => 'offline' as PresenceStatus,
      setPresence: () => {},
      agentsByTeam: AGENTS_BY_TEAM,
    };
  }
  return context;
}
