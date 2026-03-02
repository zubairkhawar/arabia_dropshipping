'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

const STORAGE_KEY = 'agents-data';

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
  { id: 'agent-1', email: 'agent@example.com', name: 'Support Agent', password: 'changeme', avatarUrl: null },
];

function loadFromStorage(): AgentsData {
  if (typeof window === 'undefined') {
    return { agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { agents: defaultAgents, currentAgentId: defaultAgents[0]?.id ?? null };
    const parsed = JSON.parse(raw) as AgentsData;
    return {
      agents: Array.isArray(parsed.agents) && parsed.agents.length > 0 ? parsed.agents : defaultAgents,
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
      const id = `agent-${Date.now()}`;
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

  return (
    <AgentsContext.Provider
      value={{
        agents: data.agents,
        currentAgentId: data.currentAgentId,
        setCurrentAgentId,
        getCurrentAgent,
        addAgent,
        updateAgent,
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
    };
  }
  return context;
}
