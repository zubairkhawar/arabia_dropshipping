'use client';

import { useMemo } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

const SM = 36;
const MD = 56;
const DOT_SM = 10;
const DOT_MD = 11;

/** Center of status dot on the bottom-right arc of the circle (half in / half out). */
function StatusDot({ online, facePx, dotPx }: { online: boolean; facePx: number; dotPx: number }) {
  const R = facePx / 2;
  const along = R / Math.SQRT2;
  return (
    <span
      className={`pointer-events-none absolute z-10 rounded-full shadow-sm ring-2 ring-white ${
        online ? 'bg-status-success' : 'bg-text-muted'
      }`}
      style={{
        width: dotPx,
        height: dotPx,
        left: `calc(50% + ${along}px - ${dotPx / 2}px)`,
        top: `calc(50% + ${along}px - ${dotPx / 2}px)`,
      }}
      aria-hidden
    />
  );
}

function AgentFace({
  agent,
  online,
  size,
}: {
  agent: { name: string; avatarUrl: string | null };
  online: boolean;
  size: 'sm' | 'md';
}) {
  const facePx = size === 'sm' ? SM : MD;
  const dotPx = size === 'sm' ? DOT_SM : DOT_MD;
  const text = size === 'sm' ? 'text-xs' : 'text-lg';
  return (
    <div className="relative shrink-0" style={{ width: facePx, height: facePx }}>
      <div
        className={`flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-primary/10 font-semibold text-primary ${text}`}
      >
        {agent.avatarUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={agent.avatarUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          agent.name.charAt(0).toUpperCase()
        )}
      </div>
      <StatusDot online={online} facePx={facePx} dotPx={dotPx} />
    </div>
  );
}

/**
 * Vertical stack of other agents’ avatars for My Chats only.
 */
export function InboxAgentPresenceStack() {
  const { agents, getCurrentAgent } = useAgents();
  const current = getCurrentAgent();

  const sorted = useMemo(() => {
    const list = agents.filter((a) => current == null || a.id !== current.id);
    list.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    return list;
  }, [agents, current?.id]);

  if (sorted.length === 0) {
    return (
      <p className="max-w-[2.75rem] text-center text-[9px] leading-tight text-text-muted">No others</p>
    );
  }

  return (
    <>
      {sorted.map((agent) => {
        const online = agent.status === 'online';
        return (
          <div key={agent.id} className="group flex w-full justify-center py-1.5">
            {/* Anchor popover to avatar-sized box so it never sits over the rail avatar */}
            <div className="relative shrink-0 translate-x-6">
              <button
                type="button"
                className="relative block shrink-0 outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-primary"
                aria-label={`${agent.name}, ${agent.email}, agent ID ${agent.id}`}
              >
                <AgentFace agent={agent} online={online} size="sm" />
              </button>

              <div
                className="pointer-events-none invisible absolute left-full top-1/2 z-[70] ml-3 -translate-y-1/2 opacity-0 transition-opacity duration-150 ease-out group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                role="tooltip"
              >
                <div className="w-max max-w-[min(88vw,260px)] rounded-xl border border-border bg-white px-3 py-2.5 shadow-xl">
                  <div className="flex items-center gap-3">
                    <AgentFace agent={agent} online={online} size="md" />
                    <div className="min-w-0 max-w-[14rem] flex-1 space-y-0.5">
                    <p className="truncate text-sm font-semibold leading-tight text-text-primary">{agent.name}</p>
                    <p className="truncate text-xs leading-snug text-text-secondary">{agent.email}</p>
                    <p className="font-mono text-[11px] leading-tight text-text-muted">ID: {agent.id}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}
