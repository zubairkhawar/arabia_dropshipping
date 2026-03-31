'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useTeams } from '@/contexts/TeamsContext';
import { useAgents } from '@/contexts/AgentsContext';

const STORAGE_KEY = 'agent-presence';

export type PresenceStatus = 'active' | 'offline';
export interface PresenceMember {
  agentId: string;
  slug: string;
  name: string;
}

export interface PresenceTeamGroup {
  team: string;
  members: PresenceMember[];
}

export function getSlugByName(name: string): string | null {
  const normalized = name.trim();
  if (!normalized) return null;
  return normalized
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
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
  agentsByTeam: PresenceTeamGroup[];
}

const AgentPresenceContext = createContext<AgentPresenceContextType | undefined>(undefined);

export function AgentPresenceProvider({ children }: { children: ReactNode }) {
  const [presenceMap, setPresenceMap] = useState<Record<string, PresenceStatus>>(loadPresenceFromStorage);
  const { teams } = useTeams();
  const { agents } = useAgents();

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

  const teamGroups: PresenceTeamGroup[] = teams
    .map((team) => ({
      team: team.name,
      members: team.members
        .map((member) => ({
          agentId: member.agentId,
          name: member.name,
          slug: getSlugByName(member.name) || member.agentId,
        }))
        .filter((member) => Boolean(member.slug)),
    }))
    .filter((group) => group.members.length > 0);

  const assignedAgentIds = new Set(
    teams.flatMap((team) => team.members.map((member) => member.agentId)),
  );
  const unassignedMembers: PresenceMember[] = agents
    .filter((agent) => !assignedAgentIds.has(agent.id))
    .map((agent) => ({
      agentId: agent.id,
      name: agent.name,
      slug: getSlugByName(agent.name) || agent.id,
    }))
    .filter((member) => Boolean(member.slug));

  const agentsByTeam: PresenceTeamGroup[] =
    unassignedMembers.length > 0
      ? [...teamGroups, { team: 'Unassigned', members: unassignedMembers }]
      : teamGroups;

  return (
    <AgentPresenceContext.Provider
      value={{
        getPresence,
        setPresence,
        agentsByTeam,
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
      agentsByTeam: [] as PresenceTeamGroup[],
    };
  }
  return context;
}
