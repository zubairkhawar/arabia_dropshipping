'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useTeams } from '@/contexts/TeamsContext';
import { useAgents } from '@/contexts/AgentsContext';

export default function AgentTeamChannel() {
  const { getCurrentAgent } = useAgents();
  const { teams, getEventsForTeam } = useTeams();
  const currentAgent = getCurrentAgent();
  const team = currentAgent
    ? teams.find((t) => t.members.some((m) => m.agentId === currentAgent.id))
    : undefined;
  const teamEvents = team ? getEventsForTeam(team.id) : [];

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
