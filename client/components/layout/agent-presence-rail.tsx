'use client';

import { useMemo } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

const RAIL_W = 56;

/**
 * Slim column of tenant agent avatars between the main nav sidebar and page content.
 * Hover shows a larger preview with full name and agent id.
 */
export function AgentPresenceRail() {
  const { agents, getCurrentAgent } = useAgents();
  const current = getCurrentAgent();

  const sorted = useMemo(() => {
    const list = [...agents];
    list.sort((a, b) => {
      if (current?.id === a.id) return -1;
      if (current?.id === b.id) return 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
    return list;
  }, [agents, current?.id]);

  return (
    <aside
      className="hidden shrink-0 flex-col border-r border-border bg-white md:flex"
      style={{ width: RAIL_W }}
      aria-label="Team agents"
    >
      <div className="flex flex-1 flex-col items-center gap-1 overflow-y-auto overflow-x-visible py-3">
        {sorted.length === 0 ? (
          <p className="max-w-[3rem] text-center text-[9px] leading-tight text-text-muted">No agents</p>
        ) : (
          sorted.map((agent) => {
            const isMe = current?.id === agent.id;
            const online = agent.status === 'online';
            return (
              <div
                key={agent.id}
                className="group relative flex w-full flex-col items-center px-1 py-0.5"
              >
                <button
                  type="button"
                  className={`relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/10 text-sm font-semibold text-primary ring-offset-2 transition-shadow outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                    isMe ? 'ring-2 ring-primary ring-offset-2' : ''
                  }`}
                  aria-label={`${agent.name}, agent ID ${agent.id}`}
                >
                  {agent.avatarUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={agent.avatarUrl}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    agent.name.charAt(0).toUpperCase()
                  )}
                  <span
                    className={`pointer-events-none absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full border-2 border-white ${
                      online ? 'bg-status-success' : 'bg-text-muted'
                    }`}
                    aria-hidden
                  />
                </button>

                {/* Hover / focus preview — extends into main area; parent main avoids clipping rail */}
                <div
                  className="pointer-events-none invisible absolute left-full top-1/2 z-[60] ml-2 w-max min-w-[220px] max-w-[min(90vw,280px)] -translate-y-1/2 opacity-0 transition-all duration-150 ease-out group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                  role="tooltip"
                >
                  <div className="rounded-xl border border-border bg-white px-4 py-3 shadow-xl">
                    <div className="flex items-center gap-3">
                      <div className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/10 text-xl font-semibold text-primary">
                        {agent.avatarUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={agent.avatarUrl}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          agent.name.charAt(0).toUpperCase()
                        )}
                        <span
                          className={`absolute bottom-0.5 right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white ${
                            online ? 'bg-status-success' : 'bg-text-muted'
                          }`}
                          aria-hidden
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-text-primary">{agent.name}</p>
                        <p className="font-mono text-xs text-text-muted">ID: {agent.id}</p>
                        {isMe ? (
                          <p className="mt-0.5 text-xs font-medium text-primary">You</p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
