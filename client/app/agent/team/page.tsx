'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useTeams } from '@/contexts/TeamsContext';
import { useAgents } from '@/contexts/AgentsContext';
import Link from 'next/link';

export default function AgentTeamChannel() {
  const { getCurrentAgent } = useAgents();
  const { teams, getEventsForTeam } = useTeams();
  const currentAgent = getCurrentAgent();
  const team = currentAgent
    ? teams.find((t) => t.members.some((m) => m.agentId === currentAgent.id))
    : undefined;
  const teamEvents = team ? getEventsForTeam(team.id) : [];

  if (!team) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-white p-6 text-center">
          <h2 className="text-lg font-semibold text-text-primary">No team assigned</h2>
          <p className="mt-2 text-sm text-text-secondary">
            You have not been assigned to any team yet.
          </p>
          <Link
            href="/agent/inbox"
            className="mt-4 inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-95"
          >
            Go to My Chats
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title="# Team Channel"
          subtitle="Team coordination chat"
          teamName={team?.name ?? 'Team'}
          teamMemberNames={team?.members.map((m) => m.name) ?? []}
          teamEvents={teamEvents}
        />
      </div>
    </div>
  );
}
