'use client';

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';

const STORAGE_KEY = 'dm-middle-bar-collapsed';

function loadCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === 'true';
  } catch {
    return false;
  }
}

function saveCollapsed(value: boolean) {
  try {
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, String(value));
  } catch {
    // ignore
  }
}

interface DmLayoutContextType {
  middleBarCollapsed: boolean;
  setMiddleBarCollapsed: (value: boolean) => void;
  toggleMiddleBar: () => void;
}

const DmLayoutContext = createContext<DmLayoutContextType | undefined>(undefined);

export function DmLayoutProvider({ children }: { children: ReactNode }) {
  const [middleBarCollapsed, setMiddleBarCollapsedState] = useState(false);

  useEffect(() => {
    setMiddleBarCollapsedState(loadCollapsed());
  }, []);

  const setMiddleBarCollapsed = useCallback((value: boolean) => {
    setMiddleBarCollapsedState(value);
    saveCollapsed(value);
  }, []);

  const toggleMiddleBar = useCallback(() => {
    setMiddleBarCollapsedState((prev) => {
      const next = !prev;
      saveCollapsed(next);
      return next;
    });
  }, []);

  return (
    <DmLayoutContext.Provider
      value={{
        middleBarCollapsed,
        setMiddleBarCollapsed,
        toggleMiddleBar,
      }}
    >
      {children}
    </DmLayoutContext.Provider>
  );
}

export function useDmLayout() {
  const context = useContext(DmLayoutContext);
  if (context === undefined) {
    return {
      middleBarCollapsed: false,
      setMiddleBarCollapsed: () => {},
      toggleMiddleBar: () => {},
    };
  }
  return context;
}
