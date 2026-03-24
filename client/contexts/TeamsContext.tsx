'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

export type TeamEventType = 'member_added' | 'member_removed' | 'member_transferred';

export interface TeamEvent {
  id: string;
  teamId: string;
  type: TeamEventType;
  memberName: string;
  targetTeamName?: string;
  sentAt: string;
}

export interface TeamMember {
  agentId: string;
  name: string;
}

export interface Team {
  id: string;
  name: string;
  description: string;
  members: TeamMember[];
}

interface TeamsData {
  teams: Team[];
  events: TeamEvent[];
}

interface TeamApiMembership {
  agent_id: number;
  team_id: number;
}

interface TeamApiModel {
  id: number;
  tenant_id: number;
  name: string;
  description: string | null;
  members: TeamApiMembership[];
}

interface TeamEventApiModel {
  id: number;
  event_type: TeamEventType;
  actor_agent_id: number | null;
  target_agent_id: number | null;
  payload: { from_team_id?: number };
  created_at: string;
}

interface AgentApiModel {
  id: number;
  email: string;
  full_name: string | null;
}

interface TeamsContextType {
  teams: Team[];
  events: TeamEvent[];
  isLoading: boolean;
  getTeam: (teamId: string) => Team | undefined;
  getTeamByName: (name: string) => Team | undefined;
  getEventsForTeam: (teamId: string) => TeamEvent[];
  addMemberToTeam: (teamId: string, agentId: string) => Promise<boolean>;
  removeMemberFromTeam: (teamId: string, agentId: string) => Promise<boolean>;
  transferMember: (fromTeamId: string, agentId: string, toTeamId: string) => Promise<boolean>;
  addTeam: (name: string, description: string) => Promise<boolean>;
  removeTeam: (teamId: string) => Promise<boolean>;
  refreshTeams: () => Promise<boolean>;
}

const TeamsContext = createContext<TeamsContextType | undefined>(undefined);

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const DEFAULT_TENANT_ID = 1;

export function TeamsProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<TeamsData>({ teams: [], events: [] });
  const [isLoading, setIsLoading] = useState(true);

  const fetchAgentNameMap = useCallback(async () => {
    const res = await fetch(`${API_BASE_URL}/api/agents?tenant_id=${DEFAULT_TENANT_ID}`, {
      method: 'GET',
    });
    if (!res.ok) return new Map<string, string>();
    const agents = (await res.json()) as AgentApiModel[];
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(String(agent.id), agent.full_name || agent.email.split('@')[0] || `Agent ${agent.id}`);
    }
    return map;
  }, []);

  const refreshTeams = useCallback(async () => {
    try {
      const [nameMap, teamsRes] = await Promise.all([
        fetchAgentNameMap(),
        fetch(`${API_BASE_URL}/api/teams?tenant_id=${DEFAULT_TENANT_ID}`, {
          method: 'GET',
        }),
      ]);
      if (!teamsRes.ok) return false;

      const teamsApi = (await teamsRes.json()) as TeamApiModel[];
      const teamsById = new Map<string, Team>();
      const teams = teamsApi.map((t) => {
        const mapped: Team = {
          id: String(t.id),
          name: t.name,
          description: t.description ?? '',
          members: (t.members || []).map((m) => ({
            agentId: String(m.agent_id),
            name: nameMap.get(String(m.agent_id)) || `Agent ${m.agent_id}`,
          })),
        };
        teamsById.set(mapped.id, mapped);
        return mapped;
      });

      const eventResponses = await Promise.all(
        teams.map((team) =>
          fetch(`${API_BASE_URL}/api/teams/${team.id}/events?tenant_id=${DEFAULT_TENANT_ID}`, {
            method: 'GET',
          }),
        ),
      );

      const events: TeamEvent[] = [];
      for (let i = 0; i < eventResponses.length; i += 1) {
        const team = teams[i];
        const response = eventResponses[i];
        if (!response.ok) continue;
        const eventRows = (await response.json()) as TeamEventApiModel[];
        for (const row of eventRows) {
          const fromTeamId = row.payload?.from_team_id ? String(row.payload.from_team_id) : undefined;
          const targetTeamName = row.event_type === 'member_transferred'
            ? team.name
            : fromTeamId
              ? teamsById.get(fromTeamId)?.name
              : undefined;
          events.push({
            id: String(row.id),
            teamId: team.id,
            type: row.event_type,
            memberName: row.target_agent_id ? nameMap.get(String(row.target_agent_id)) || `Agent ${row.target_agent_id}` : 'Agent',
            targetTeamName,
            sentAt: row.created_at,
          });
        }
      }

      setData({ teams, events });
      return true;
    } catch {
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [fetchAgentNameMap]);

  useEffect(() => {
    void refreshTeams();
  }, [refreshTeams]);

  const getTeam = useCallback(
    (teamId: string) => data.teams.find((t) => t.id === teamId),
    [data.teams],
  );

  const getTeamByName = useCallback(
    (name: string) => data.teams.find((t) => t.name === name),
    [data.teams],
  );

  const getEventsForTeam = useCallback(
    (teamId: string) =>
      data.events
        .filter((e) => e.teamId === teamId)
        .sort((a, b) => new Date(a.sentAt).getTime() - new Date(b.sentAt).getTime()),
    [data.events],
  );

  const addMemberToTeam = useCallback(
    async (teamId: string, agentId: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/teams/${teamId}/members`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tenant_id: DEFAULT_TENANT_ID,
            agent_id: Number(agentId),
          }),
        });
        if (!res.ok) return false;
        return refreshTeams();
      } catch {
        return false;
      }
    },
    [refreshTeams],
  );

  const removeMemberFromTeam = useCallback(
    async (teamId: string, agentId: string) => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/teams/${teamId}/members/${agentId}?tenant_id=${DEFAULT_TENANT_ID}`,
          {
            method: 'DELETE',
          },
        );
        if (!res.ok) return false;
        return refreshTeams();
      } catch {
        return false;
      }
    },
    [refreshTeams],
  );

  const transferMember = useCallback(
    async (fromTeamId: string, agentId: string, toTeamId: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/teams/transfer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tenant_id: DEFAULT_TENANT_ID,
            agent_id: Number(agentId),
            from_team_id: Number(fromTeamId),
            to_team_id: Number(toTeamId),
          }),
        });
        if (!res.ok) return false;
        return refreshTeams();
      } catch {
        return false;
      }
    },
    [refreshTeams],
  );

  const addTeam = useCallback(
    async (name: string, description: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/teams`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tenant_id: DEFAULT_TENANT_ID,
            name,
            description,
          }),
        });
        if (!res.ok) return false;
        return refreshTeams();
      } catch {
        return false;
      }
    },
    [refreshTeams],
  );

  const removeTeam = useCallback(
    async (teamId: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/teams/${teamId}?tenant_id=${DEFAULT_TENANT_ID}`, {
          method: 'DELETE',
        });
        if (!res.ok) return false;
        return refreshTeams();
      } catch {
        return false;
      }
    },
    [refreshTeams],
  );

  return (
    <TeamsContext.Provider
      value={{
        teams: data.teams,
        events: data.events,
        isLoading,
        getTeam,
        getTeamByName,
        getEventsForTeam,
        addMemberToTeam,
        removeMemberFromTeam,
        transferMember,
        addTeam,
        removeTeam,
        refreshTeams,
      }}
    >
      {children}
    </TeamsContext.Provider>
  );
}

export function useTeams() {
  const context = useContext(TeamsContext);
  if (context === undefined) {
    return {
      teams: [] as Team[],
      events: [] as TeamEvent[],
      isLoading: false,
      getTeam: (_id: string) => undefined,
      getTeamByName: (_name: string) => undefined,
      getEventsForTeam: (_id: string) => [] as TeamEvent[],
      addMemberToTeam: async () => false,
      removeMemberFromTeam: async () => false,
      transferMember: async () => false,
      addTeam: async () => false,
      removeTeam: async () => false,
      refreshTeams: async () => false,
    };
  }
  return context;
}
