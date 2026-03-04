'use client';

import { useState } from 'react';
import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { PanelRightOpen, SquareChevronRight, Search, Filter } from 'lucide-react';

type MonitoringMode = 'passive' | 'assisted' | 'intervene';

function FilterPanel() {
  return (
    <div className="hidden lg:flex w-64 shrink-0 flex-col border-r border-border bg-panel p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Filters</h3>
        <Filter className="h-4 w-4 text-text-muted" />
      </div>
      <div className="space-y-2 text-xs">
        <p className="text-text-muted uppercase tracking-wide">Handler</p>
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" defaultChecked />
            AI Active
          </label>
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" defaultChecked />
            Human Active
          </label>
        </div>
      </div>
      <div className="space-y-2 text-xs">
        <p className="text-text-muted uppercase tracking-wide">Routing</p>
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            Team A
          </label>
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            Team B
          </label>
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            Unassigned
          </label>
        </div>
      </div>
      <div className="space-y-2 text-xs">
        <p className="text-text-muted uppercase tracking-wide">Priority</p>
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            Escalated
          </label>
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            High Value
          </label>
          <label className="flex items-center gap-2 text-text-secondary">
            <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
            Flagged
          </label>
        </div>
      </div>
    </div>
  );
}

function AnalyticsPanel() {
  return (
    <div className="hidden xl:block w-80 2xl:w-96 shrink-0 border-l border-border bg-panel p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Live Analytics</h3>
      <div className="space-y-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">AI Resolution Rate</span>
          <span className="font-semibold text-text-primary">87.5%</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Human Load (now)</span>
          <span className="font-semibold text-text-primary">34 agents</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Escalated</span>
          <span className="font-semibold text-status-warning">12</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">At Risk (SLA)</span>
          <span className="font-semibold text-status-error">5</span>
        </div>
      </div>
      <div className="mt-4 border-t border-border pt-4 space-y-3">
        <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
          Routing Snapshot
        </p>
        <div className="space-y-2">
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-text-secondary">AI</span>
              <span className="text-text-primary">82%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/60 overflow-hidden">
              <div className="h-full w-[82%] bg-primary rounded-full" />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-text-secondary">Agents</span>
              <span className="text-text-primary">18%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/60 overflow-hidden">
              <div className="h-full w-[18%] bg-status-info rounded-full" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AdminInboxContent() {
  const { chatListCollapsed, contextCollapsed, setChatListCollapsed, setContextCollapsed } = useInboxPanels();
  const [mode, setMode] = useState<MonitoringMode>('passive');

  return (
    <div className="flex h-full">
      <FilterPanel />

      {chatListCollapsed ? (
        <div className="hidden md:flex w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-panel py-4">
          <button
            type="button"
            onClick={() => setChatListCollapsed(false)}
            className="rounded p-2.5 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand conversations"
          >
            <SquareChevronRight className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded p-2.5 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Search"
          >
            <Search className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-panel shrink-0">
          <ChatList />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-white">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-muted uppercase tracking-wide">Monitoring Mode</span>
            <div className="inline-flex rounded-full border border-border bg-panel p-0.5">
              {(['passive', 'assisted', 'intervene'] as MonitoringMode[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMode(value)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    mode === value
                      ? value === 'intervene'
                        ? 'bg-status-error text-white'
                        : 'bg-primary text-white'
                      : 'text-text-secondary'
                  }`}
                >
                  {value === 'passive' && 'Passive'}
                  {value === 'assisted' && 'Assisted'}
                  {value === 'intervene' && 'Intervene'}
                </button>
              ))}
            </div>
          </div>
          <p className="text-[11px] text-text-secondary">
            {mode === 'passive' && 'View-only. Admin cannot intervene.'}
            {mode === 'assisted' && 'Assisted mode. Use notes & routing without replying as agent.'}
            {mode === 'intervene' && 'Intervene mode. You are temporarily acting as the agent.'}
          </p>
        </div>
        <div className="relative flex-1">
          <ChatWindow />
          {mode !== 'intervene' && (
            <div className="pointer-events-auto absolute inset-0 bg-white/60 flex items-center justify-center">
              <div className="px-6 py-3 rounded-full border border-border bg-white shadow-sm text-xs text-text-secondary">
                {mode === 'passive'
                  ? 'Passive Monitor — live view only. Switch to Intervene to take over this conversation.'
                  : 'Assisted Mode — add routing decisions and notes from side panels. Switch to Intervene to reply as the agent.'}
              </div>
            </div>
          )}
        </div>
      </div>

      {contextCollapsed ? (
        <div className="hidden lg:flex w-12 shrink-0 flex-col items-center border-l border-border bg-panel pt-4">
          <button
            type="button"
            onClick={() => setContextCollapsed(false)}
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand analytics"
          >
            <PanelRightOpen className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <AnalyticsPanel />
      )}
    </div>
  );
}

export default function AdminInbox() {
  return (
    <InboxPanelsProvider>
      <AdminInboxContent />
    </InboxPanelsProvider>
  );
}
