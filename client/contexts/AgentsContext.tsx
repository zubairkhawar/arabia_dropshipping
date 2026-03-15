'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

const STORAGE_KEY = 'agents-data';

/** Agent unique ID is set by the backend when the admin creates a new agent. */
export interface AgentRecord {
  id: string;
  email: string;
  name: string;
  password: string;
  avatarUrl: string | null;
}

interface AgentsData {
  agents: AgentRecord[];
  currentAgentId: string | null;
}

const defaultAgents: AgentRecord[] = [
  { id: '1001', email: 'agent@example.com', name: 'Support Agent', password: 'changeme', avatarUrl: null },
  { id: '1002', email: 'hamza@example.com', name: 'Hamza', password: 'changeme', avatarUrl: null },
  { id: '1003', email: 'sarah@example.com', name: 'Sarah', password: 'changeme', avatarUrl: null },
];

/** 4-digit numeric ID (e.g. 1001). Old formats like agent01 are migrated to this. */
function isNumericAgentId(id: string): boolean {
  return /^\d{4}$/.test(id);
}

function migrateAgentsToNumericIds(agents: AgentRecord[]): AgentRecord[] {
  const usedIds = new Set(agents.filter((a) => isNumericAgentId(a.id)).map((a) => a.id));
  let nextId = 1001;
  const nextNumericId = () => {
    while (usedIds.has(String(nextId))) nextId++;
    const id = String(nextId);
    usedIds.add(id);
    nextId++;
    return id;
  };
  return agents.map((a) =>
    isNumericAgentId(a.id) ? a : { ...a, id: nextNumericId() },
  );
}

function loadFromStorage(): AgentsData {
  if (typeof window === 'undefined') {
    return { agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null };
    const parsed = JSON.parse(raw) as AgentsData;
    let agents =
      Array.isArray(parsed.agents) && parsed.agents.length > 0 ? parsed.agents : defaultAgents;
    const hasLegacyIds = agents.some((a) => !isNumericAgentId(a.id));
    if (hasLegacyIds) {
      const idMap = new Map<string, string>();
      const migrated = migrateAgentsToNumericIds(agents);
      agents.forEach((a, i) => {
        if (!isNumericAgentId(a.id)) idMap.set(a.id, migrated[i].id);
      });
      agents = migrated;
      let currentAgentId = parsed.currentAgentId ?? parsed.agents?.[0]?.id ?? null;
      if (currentAgentId && idMap.has(currentAgentId)) {
        currentAgentId = idMap.get(currentAgentId) ?? currentAgentId;
      }
      saveToStorage({ agents, currentAgentId });
      return { agents, currentAgentId };
    }
    return {
      agents,
      currentAgentId: parsed.currentAgentId ?? parsed.agents?.[0]?.id ?? null,
    };
  } catch {
    return { agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null };
  }
}

function saveToStorage(data: AgentsData) {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    }
  } catch {
    // ignore
  }
}

interface AgentsContextType {
  agents: AgentRecord[];
  currentAgentId: string | null;
  setCurrentAgentId: (id: string | null) => void;
  getCurrentAgent: () => AgentRecord | null;
  addAgent: (email: string, name: string, password: string) => void;
  updateAgent: (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => void;
  removeAgent: (id: string) => void;
}

const AgentsContext = createContext<AgentsContextType | undefined>(undefined);

export function AgentsProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AgentsData>({ agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null });

  useEffect(() => {
    setData(loadFromStorage());
  }, []);

  const persist = useCallback((next: AgentsData) => {
    setData(next);
    saveToStorage(next);
  }, []);

  const getCurrentAgent = useCallback(() => {
    if (!data.currentAgentId) return null;
    return data.agents.find((a) => a.id === data.currentAgentId) ?? null;
  }, [data.agents, data.currentAgentId]);

  const setCurrentAgentId = useCallback(
    (id: string | null) => {
      persist({ ...data, currentAgentId: id });
    },
    [data, persist],
  );

  const addAgent = useCallback(
    (email: string, name: string, password: string) => {
      // In production, the backend creates the agent and returns the generated id.
      const id = String(Math.floor(1000 + Math.random() * 9000));
      const newAgent: AgentRecord = { id, email, name, password, avatarUrl: null };
      persist({ ...data, agents: [...data.agents, newAgent] });
    },
    [data, persist],
  );

  const updateAgent = useCallback(
    (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => {
      const nextAgents = data.agents.map((a) => (a.id === id ? { ...a, ...updates } : a));
      persist({ ...data, agents: nextAgents });
    },
    [data, persist],
  );

  const removeAgent = useCallback(
    (id: string) => {
      const nextAgents = data.agents.filter((a) => a.id !== id);
      const nextCurrentId =
        data.currentAgentId === id ? (nextAgents[0]?.id ?? null) : data.currentAgentId;
      persist({ agents: nextAgents, currentAgentId: nextCurrentId });
    },
    [data, persist],
  );

  return (
    <AgentsContext.Provider
      value={{
        agents: data.agents,
        currentAgentId: data.currentAgentId,
        setCurrentAgentId,
        getCurrentAgent,
        addAgent,
        updateAgent,
        removeAgent,
      }}
    >
      {children}
    </AgentsContext.Provider>
  );
}

export function useAgents() {
  const context = useContext(AgentsContext);
  if (context === undefined) {
    return {
      agents: defaultAgents,
      currentAgentId: null,
      setCurrentAgentId: () => {},
      getCurrentAgent: () => defaultAgents[0] ?? null,
      addAgent: () => {},
      updateAgent: () => {},
      removeAgent: () => {},
    };
  }
  return context;
}
