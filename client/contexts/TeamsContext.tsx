'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

const STORAGE_KEY = 'teams-data';

export type TeamEventType = 'member_added' | 'member_removed' | 'member_transferred';

export interface TeamEvent {
  id: string;
  teamId: string;
  type: TeamEventType;
  memberName: string;
  targetTeamName?: string;
  sentAt: string;
}

export interface Team {
  id: string;
  name: string;
  description: string;
  members: string[];
}

interface TeamsData {
  teams: Team[];
  events: TeamEvent[];
}

const defaultTeams: Team[] = [
  {
    id: 'team-a',
    name: 'Team A',
    description: 'Primary WhatsApp support team.',
    members: ['Ali', 'Hamza', 'Sarah'],
  },
  { id: 'team-b', name: 'Team B', description: '', members: [] },
  { id: 'team-c', name: 'Team C', description: '', members: [] },
];

function loadFromStorage(): TeamsData {
  if (typeof window === 'undefined') return { teams: defaultTeams, events: [] };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { teams: defaultTeams, events: [] };
    const parsed = JSON.parse(raw) as TeamsData;
    const teams: Team[] =
      Array.isArray(parsed.teams) && parsed.teams.length > 0 ? parsed.teams : defaultTeams;
    const normalisedTeams = teams.map((t) => ({
      ...t,
      description: t.description ?? '',
    }));
    return {
      teams: normalisedTeams,
      events: Array.isArray(parsed.events) ? parsed.events : [],
    };
  } catch {
    return { teams: defaultTeams, events: [] };
  }
}

function saveToStorage(data: TeamsData) {
  try {
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

interface TeamsContextType {
  teams: Team[];
  events: TeamEvent[];
  getTeam: (teamId: string) => Team | undefined;
  getTeamByName: (name: string) => Team | undefined;
  getEventsForTeam: (teamId: string) => TeamEvent[];
  addMemberToTeam: (teamId: string, memberName: string) => void;
  removeMemberFromTeam: (teamId: string, memberName: string) => void;
  transferMember: (fromTeamId: string, memberName: string, toTeamId: string) => void;
  addTeam: (name: string, description: string) => void;
  removeTeam: (teamId: string) => void;
}

const TeamsContext = createContext<TeamsContextType | undefined>(undefined);

export function TeamsProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<TeamsData>({ teams: defaultTeams, events: [] });

  useEffect(() => {
    setData(loadFromStorage());
  }, []);

  const persist = useCallback((next: TeamsData) => {
    setData(next);
    saveToStorage(next);
  }, []);

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
      data.events.filter((e) => e.teamId === teamId).sort((a, b) => new Date(a.sentAt).getTime() - new Date(b.sentAt).getTime()),
    [data.events],
  );

  const addMemberToTeam = useCallback(
    (teamId: string, memberName: string) => {
      const team = data.teams.find((t) => t.id === teamId);
      if (!team || team.members.includes(memberName)) return;
      const nextTeams = data.teams.map((t) =>
        t.id === teamId ? { ...t, members: [...t.members, memberName] } : t,
      );
      const event: TeamEvent = {
        id: `ev-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        teamId,
        type: 'member_added',
        memberName,
        sentAt: new Date().toISOString(),
      };
      persist({ teams: nextTeams, events: [...data.events, event] });
    },
    [data, persist],
  );

  const removeMemberFromTeam = useCallback(
    (teamId: string, memberName: string) => {
      const team = data.teams.find((t) => t.id === teamId);
      if (!team || !team.members.includes(memberName)) return;
      const nextTeams = data.teams.map((t) =>
        t.id === teamId ? { ...t, members: t.members.filter((m) => m !== memberName) } : t,
      );
      const event: TeamEvent = {
        id: `ev-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        teamId,
        type: 'member_removed',
        memberName,
        sentAt: new Date().toISOString(),
      };
      persist({ teams: nextTeams, events: [...data.events, event] });
    },
    [data, persist],
  );

  const transferMember = useCallback(
    (fromTeamId: string, memberName: string, toTeamId: string) => {
      const fromTeam = data.teams.find((t) => t.id === fromTeamId);
      const toTeam = data.teams.find((t) => t.id === toTeamId);
      if (!fromTeam || !toTeam || !fromTeam.members.includes(memberName)) return;
      if (fromTeamId === toTeamId) return;
      const nextTeams = data.teams.map((t) => {
        if (t.id === fromTeamId) return { ...t, members: t.members.filter((m) => m !== memberName) };
        if (t.id === toTeamId) return { ...t, members: [...t.members, memberName] };
        return t;
      });
      const event: TeamEvent = {
        id: `ev-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        teamId: fromTeamId,
        type: 'member_transferred',
        memberName,
        targetTeamName: toTeam.name,
        sentAt: new Date().toISOString(),
      };
      persist({ teams: nextTeams, events: [...data.events, event] });
    },
    [data, persist],
  );

  const addTeam = useCallback(
    (name: string, description: string) => {
      const id = `team-${name.toLowerCase().replace(/\s+/g, '-')}`;
      if (data.teams.some((t) => t.id === id)) return;
      const team: Team = { id, name, description, members: [] };
      persist({ teams: [...data.teams, team], events: data.events });
    },
    [data, persist],
  );

  const removeTeam = useCallback(
    (teamId: string) => {
      const nextTeams = data.teams.filter((t) => t.id !== teamId);
      const nextEvents = data.events.filter((e) => e.teamId !== teamId);
      persist({ teams: nextTeams, events: nextEvents });
    },
    [data, persist],
  );

  return (
    <TeamsContext.Provider
      value={{
        teams: data.teams,
        events: data.events,
        getTeam,
        getTeamByName,
        getEventsForTeam,
        addMemberToTeam,
        removeMemberFromTeam,
        transferMember,
        addTeam,
        removeTeam,
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
      teams: defaultTeams,
      events: [] as TeamEvent[],
      getTeam: (id: string) => defaultTeams.find((t) => t.id === id),
      getTeamByName: (name: string) => defaultTeams.find((t) => t.name === name),
      getEventsForTeam: (_id: string) => [] as TeamEvent[],
      addMemberToTeam: () => {},
      removeMemberFromTeam: () => {},
      transferMember: () => {},
      addTeam: () => {},
      removeTeam: () => {},
    };
  }
  return context;
}
