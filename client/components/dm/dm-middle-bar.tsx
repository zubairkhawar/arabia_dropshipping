'use client';

import { useRef, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { MessageSquarePlus, ChevronLeft, ChevronRight, MoreVertical, Search, Trash2 } from 'lucide-react';
import { useAgentPresence } from '@/contexts/AgentPresenceContext';
import { useDmChats } from '@/contexts/DmChatsContext';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { useDmLayout } from '@/contexts/DmLayoutContext';

const DM_MIDDLE_BAR_WIDTH = 280;
const DM_MIDDLE_BAR_COLLAPSED_WIDTH = 56;

export function DmMiddleBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { conversations, addOrUpdateConversation, removeConversation } = useDmChats();
  const { getPresence, agentsByTeam } = useAgentPresence();
  const { fullName } = useAgentProfile();
  const { middleBarCollapsed, toggleMiddleBar } = useDmLayout();
  const [showDropup, setShowDropup] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [menuSlug, setMenuSlug] = useState<string | null>(null);
  const dropupRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropupRef.current && !dropupRef.current.contains(e.target as Node)) {
        setShowDropup(false);
      }
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuSlug(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentSlug = pathname?.startsWith('/agent/dm/')
    ? (pathname.replace('/agent/dm/', '').split('/')[0] || null)
    : null;

  const filteredConversations = searchQuery.trim()
    ? conversations.filter(
        (c) => c.name.toLowerCase().includes(searchQuery.trim().toLowerCase()),
      )
    : conversations;

  const handleDeleteChat = (slug: string) => {
    removeConversation(slug);
    setMenuSlug(null);
    if (currentSlug === slug) {
      router.push('/agent/dm');
    }
  };

  const focusSearch = () => {
    if (middleBarCollapsed) toggleMiddleBar();
    setTimeout(() => searchInputRef.current?.focus(), 100);
  };

  const width = middleBarCollapsed ? DM_MIDDLE_BAR_COLLAPSED_WIDTH : DM_MIDDLE_BAR_WIDTH;

  return (
    <div
      className="flex flex-col h-full border-r border-border bg-white shrink-0 transition-[width] duration-200"
      style={{ width }}
    >
      {/* Top row: 64px when expanded (align with chat header); when collapsed allow height for expand + new chat + search */}
      <div
        className={`flex shrink-0 ${middleBarCollapsed ? 'flex-col items-center justify-center gap-2 py-3' : 'items-center gap-2 p-2 h-[64px] border-b border-border'}`}
      >
        {middleBarCollapsed ? (
          <div className="flex flex-col items-center gap-2 w-full">
            <button
              type="button"
              onClick={toggleMiddleBar}
              className="p-2 rounded-lg text-text-secondary hover:bg-white hover:text-text-primary transition-colors"
              aria-label="Expand chat list"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
            <div ref={dropupRef} className="relative">
              <button
                type="button"
                onClick={() => setShowDropup(!showDropup)}
                className="p-2 rounded-lg text-text-secondary hover:bg-white hover:text-primary transition-colors"
                title="New chat"
                aria-label="Start new direct message"
              >
                <MessageSquarePlus className="w-5 h-5" />
              </button>
              {showDropup && (
                <div className="absolute left-full top-0 ml-1 w-64 max-h-80 overflow-y-auto rounded-xl border border-border bg-card shadow-lg z-50 py-2">
                  <p className="px-4 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Start a conversation
                  </p>
                  {agentsByTeam.map((group) => (
                    <div key={group.team} className="px-2 py-1">
                      <p className="px-2 py-1 text-xs font-medium text-text-secondary">{group.team}</p>
                      <ul className="space-y-0.5">
                        {group.members.map((member) => {
                          const status = getPresence(member.slug);
                          const isCurrentUser =
                            fullName.trim().toLowerCase() === member.name.trim().toLowerCase();
                          return (
                            <li key={member.slug}>
                              <Link
                                href={`/agent/dm/${member.slug}`}
                                onClick={() => {
                                  addOrUpdateConversation(member.slug, member.name);
                                  setShowDropup(false);
                                }}
                                className={`flex items-center gap-3 rounded-lg px-3 py-2 transition-colors ${
                                  isCurrentUser
                                    ? 'opacity-60 cursor-default pointer-events-none'
                                    : 'hover:bg-panel text-text-primary'
                                }`}
                              >
                                <div className="relative flex-shrink-0">
                                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">
                                    {member.name.charAt(0)}
                                  </div>
                                  <span
                                    className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-card ${
                                      status === 'active' ? 'bg-status-success' : 'bg-text-muted'
                                    }`}
                                  />
                                </div>
                                <span className="font-medium text-sm">{member.name}</span>
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={focusSearch}
              className="p-2 rounded-lg text-text-secondary hover:bg-white hover:text-text-primary transition-colors"
              title="Search conversations"
              aria-label="Search"
            >
              <Search className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={toggleMiddleBar}
              className="p-2 rounded-lg text-text-secondary hover:bg-white hover:text-text-primary transition-colors shrink-0"
              aria-label="Collapse chat list"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div className="flex-1 min-w-0 relative">
              <Search className="w-4 h-4 text-text-muted shrink-0 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-lg bg-white placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
            </div>
            <div ref={dropupRef} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setShowDropup(!showDropup)}
                className="p-2 rounded-full bg-primary text-white hover:bg-primary/90 transition-colors"
                title="New chat"
                aria-label="Start new direct message"
              >
                <MessageSquarePlus className="w-5 h-5" />
              </button>
              {showDropup && (
                <div className="absolute right-0 top-full mt-2 w-64 max-h-80 overflow-y-auto rounded-xl border border-border bg-card shadow-lg z-50 py-2">
                  <p className="px-4 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Start a conversation
                  </p>
                  {agentsByTeam.map((group) => (
                    <div key={group.team} className="px-2 py-1">
                      <p className="px-2 py-1 text-xs font-medium text-text-secondary">{group.team}</p>
                      <ul className="space-y-0.5">
                        {group.members.map((member) => {
                          const status = getPresence(member.slug);
                          const isCurrentUser =
                            fullName.trim().toLowerCase() === member.name.trim().toLowerCase();
                          return (
                            <li key={member.slug}>
                              <Link
                                href={`/agent/dm/${member.slug}`}
                                onClick={() => {
                                  addOrUpdateConversation(member.slug, member.name);
                                  setShowDropup(false);
                                }}
                                className={`flex items-center gap-3 rounded-lg px-3 py-2 transition-colors ${
                                  isCurrentUser
                                    ? 'opacity-60 cursor-default pointer-events-none'
                                    : 'hover:bg-panel text-text-primary'
                                }`}
                              >
                                <div className="relative flex-shrink-0">
                                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">
                                    {member.name.charAt(0)}
                                  </div>
                                  <span
                                    className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-card ${
                                      status === 'active' ? 'bg-status-success' : 'bg-text-muted'
                                    }`}
                                  />
                                </div>
                                <span className="font-medium text-sm">{member.name}</span>
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Conversation list - hidden when collapsed */}
      {!middleBarCollapsed && (
        <div className="flex-1 overflow-y-auto min-h-0">
          <div className="p-2">
            {filteredConversations.length === 0 ? (
              <p className="text-sm text-text-muted px-3 py-4">
                {searchQuery.trim() ? 'No matches' : 'No conversations yet'}
              </p>
            ) : (
              <ul className="space-y-0.5">
                {filteredConversations.map((c) => {
                  const isActive = currentSlug === c.slug;
                  const status = getPresence(c.slug);
                  const menuOpen = menuSlug === c.slug;
                  return (
                    <li
                      key={c.slug}
                      className={`group rounded-lg ${isActive ? 'bg-primary/10' : ''}`}
                    >
                      <div className="flex items-center gap-0 min-w-0">
                        <Link
                          href={`/agent/dm/${c.slug}`}
                          className={`flex items-center gap-3 rounded-l-lg px-3 py-2.5 transition-colors min-w-0 flex-1 ${
                            isActive
                              ? 'text-primary'
                              : 'text-text-secondary hover:bg-white hover:text-text-primary'
                          }`}
                        >
                          <div className="relative flex-shrink-0">
                            <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">
                              {c.name.charAt(0)}
                            </div>
                            <span
                              className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-panel ${
                                status === 'active' ? 'bg-status-success' : 'bg-text-muted'
                              }`}
                            />
                          </div>
                          <div className="min-w-0 flex-1">
                            <span className="font-medium text-sm truncate block">{c.name}</span>
                          </div>
                        </Link>
                        <div
                          ref={menuSlug === c.slug ? menuRef : undefined}
                          className="relative shrink-0 pr-1"
                        >
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setMenuSlug(menuOpen ? null : c.slug);
                            }}
                            className={`p-1.5 rounded-lg transition-colors ${
                              menuOpen
                                ? 'bg-white text-primary'
                                : 'text-text-muted hover:bg-white hover:text-text-primary opacity-0 group-hover:opacity-100'
                            }`}
                            aria-label="Conversation options"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {menuOpen && (
                            <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-border bg-card shadow-lg z-50 py-1">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  if (confirm(`Delete conversation with ${c.name}?`)) {
                                    handleDeleteChat(c.slug);
                                  }
                                }}
                                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-status-error hover:bg-panel text-left"
                              >
                                <Trash2 className="w-4 h-4 shrink-0" />
                                Delete chat
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Bottom spacer: same height as chat input bar (80px) so bottom separator aligns with main content */}
      {!middleBarCollapsed && (
        <div className="flex-shrink-0 h-[80px] border-t border-border" aria-hidden />
      )}
    </div>
  );
}
