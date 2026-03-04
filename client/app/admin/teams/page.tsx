'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ChatWindow } from '@/components/chat/chat-window';
import { useTeams } from '@/contexts/TeamsContext';
import { Users, UserPlus, MoreVertical, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';

export default function AdminTeams() {
  const { teams, addTeam, removeTeam, getEventsForTeam } = useTeams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [teamName, setTeamName] = useState('');
  const [menuTeamId, setMenuTeamId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId && teams.length > 0) {
      setSelectedId(teams[0].id);
    } else if (selectedId && !teams.find((t) => t.id === selectedId)) {
      setSelectedId(teams[0]?.id ?? null);
    }
  }, [teams, selectedId]);

  const selectedTeam = useMemo(
    () => teams.find((t) => t.id === selectedId) ?? null,
    [teams, selectedId],
  );
  const teamEvents = selectedTeam ? getEventsForTeam(selectedTeam.id) : [];

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = teamName.trim();
    if (!trimmed) return;
    addTeam(trimmed);
    setTeamName('');
    setShowCreateModal(false);
  };

  const handleDelete = (id: string, name: string) => {
    if (!confirm(`Delete team "${name}"? Members will simply lose this team grouping.`)) return;
    removeTeam(id);
    if (menuTeamId === id) setMenuTeamId(null);
  };

  const width = listCollapsed ? 64 : 260;

  return (
    <div className="flex h-full">
      <div
        className="flex flex-col h-full border-r border-border bg-white shrink-0 transition-[width] duration-200"
        style={{ width }}
      >
        <div
          className={`flex items-center ${
            listCollapsed ? 'justify-center py-3' : 'justify-between px-3 py-2 h-[56px]'
          } border-b border-border`}
        >
          {listCollapsed ? (
            <button
              type="button"
              onClick={() => setListCollapsed(false)}
              className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
              aria-label="Expand teams list"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setListCollapsed(true)}
                  className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
                  aria-label="Collapse teams list"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Teams
                  </p>
                  <p className="text-[11px] text-text-secondary">
                    {teams.length} team{teams.length === 1 ? '' : 's'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors"
                aria-label="Add team"
              >
                <UserPlus className="w-4 h-4" />
                <span>Add</span>
              </button>
            </>
          )}
        </div>

        {!listCollapsed && (
          <div className="flex-1 overflow-y-auto">
            {teams.length === 0 ? (
              <p className="px-4 py-6 text-xs text-text-muted">
                No teams yet. Click “Add” to create a team.
              </p>
            ) : (
              <ul className="p-2 space-y-0.5">
                {teams.map((team) => {
                  const isActive = team.id === selectedId;
                  const menuOpen = menuTeamId === team.id;
                  return (
                    <li
                      key={team.id}
                      className={`group rounded-lg ${isActive ? 'bg-primary/5' : ''}`}
                    >
                      <div className="flex items-center min-w-0">
                        <button
                          type="button"
                          onClick={() => setSelectedId(team.id)}
                          className={`flex items-center gap-3 px-3 py-2 rounded-l-lg min-w-0 flex-1 text-left transition-colors ${
                            isActive
                              ? 'text-primary'
                              : 'text-text-secondary hover:bg-panel hover:text-text-primary'
                          }`}
                        >
                          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0">
                            <Users className="w-4 h-4" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">{team.name}</p>
                            <p className="text-[11px] text-text-muted truncate">
                              {team.members.length} member{team.members.length === 1 ? '' : 's'}
                            </p>
                          </div>
                        </button>
                        <div className="relative pr-1">
                          <button
                            type="button"
                            onClick={() =>
                              setMenuTeamId((current) =>
                                current === team.id ? null : team.id,
                              )
                            }
                            className={`p-1.5 rounded-lg transition-colors ${
                              menuOpen
                                ? 'bg-panel text-text-primary'
                                : 'text-text-muted hover:bg-panel hover:text-text-primary opacity-0 group-hover:opacity-100'
                            }`}
                            aria-label="Team options"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {menuOpen && (
                            <div className="absolute right-0 top-full mt-1 w-48 rounded-lg border border-border bg-card shadow-lg z-20 py-1">
                              <Link
                                href={`/admin/teams/${team.id}`}
                                className="flex items-center gap-2 px-3 py-2 text-xs text-text-primary hover:bg-panel"
                              >
                                Manage members
                              </Link>
                              <button
                                type="button"
                                onClick={() => handleDelete(team.id, team.name)}
                                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-status-error hover:bg-panel text-left"
                              >
                                <Trash2 className="w-4 h-4" />
                                Delete team
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
        )}
      </div>

      <div className="flex-1 min-w-0 flex">
        <div className="flex min-w-0 flex-[3] flex-col border-r border-border bg-white">
          {selectedTeam ? (
            <ChatWindow
              isInternalChat
              title="# Team Channel"
              subtitle={`Internal chat for ${selectedTeam.name}`}
              teamName={selectedTeam.name}
              teamMemberNames={selectedTeam.members}
              teamEvents={teamEvents}
              readOnly
            />
          ) : (
            <div className="flex-1 flex items-center justify-center px-6">
              <div className="text-center max-w-sm">
                <p className="text-sm font-medium text-text-primary mb-1">
                  No team selected
                </p>
                <p className="text-xs text-text-secondary mb-3">
                  Choose a team from the teams bar on the left to see its group chat and overview.
                </p>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark"
                >
                  <UserPlus className="w-4 h-4" />
                  Create first team
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex-[1.5] min-w-[240px] max-w-sm xl:max-w-md flex flex-col p-6">
          <div className="mb-4">
            <h1 className="text-2xl font-bold text-text-primary">Teams</h1>
            <p className="text-text-secondary mt-1 text-sm">
              Organize agents into routing teams. Each team can have its own load, routing rules, and
              internal channel.
            </p>
          </div>

          {selectedTeam ? (
            <div className="space-y-4">
              <div className="bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                  Team Overview
                </p>
                <h2 className="text-lg font-semibold text-text-primary">{selectedTeam.name}</h2>
                <div className="grid grid-cols-2 gap-3 text-xs mt-2">
                  <div className="p-3 rounded-lg bg-panel border border-border">
                    <p className="text-text-secondary mb-1">Members</p>
                    <p className="text-xl font-semibold text-text-primary">
                      {selectedTeam.members.length}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-panel border border-border opacity-70">
                    <p className="text-text-secondary mb-1">Active chats</p>
                    <p className="text-xl font-semibold text-text-primary">—</p>
                  </div>
                </div>
                <p className="text-[11px] text-text-muted mt-2">
                  Use this team to route conversations to a focused group of agents. Admins can
                  update members and see soft system messages in the team channel.
                </p>
              </div>

              <div className="bg-card rounded-xl border border-border shadow-sm p-6 space-y-3">
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                  Members
                </p>
                {selectedTeam.members.length === 0 ? (
                  <p className="text-xs text-text-muted">
                    No members yet. Use “Manage members” to add agents into this team.
                  </p>
                ) : (
                  <ul className="space-y-1.5 text-sm">
                    {selectedTeam.members.map((name) => (
                      <li
                        key={name}
                        className="flex items-center gap-3 px-3 py-1.5 rounded-lg bg-panel border border-border"
                      >
                        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-primary text-xs font-semibold flex-shrink-0">
                          {name.charAt(0)}
                        </div>
                        <span className="text-text-primary">{name}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="pt-3">
                  <Link
                    href={`/admin/teams/${selectedTeam.id}`}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-xs text-text-primary hover:bg-panel"
                  >
                    Manage team members
                  </Link>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {showCreateModal && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4">
              <p className="text-sm font-semibold text-text-primary">Create team</p>
              <p className="text-xs text-text-secondary mt-1">
                Give your team a clear name, like “UAE WhatsApp Support” or “Escalations”.
              </p>
            </div>
            <form onSubmit={handleCreate} className="space-y-3 text-sm">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Team name
                </label>
                <input
                  type="text"
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                  placeholder="Team A"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:bg-panel"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 px-4 py-1.5 bg-primary text-white rounded-lg text-xs font-medium hover:bg-primary-dark"
                >
                  <UserPlus className="w-4 h-4" />
                  Create team
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

