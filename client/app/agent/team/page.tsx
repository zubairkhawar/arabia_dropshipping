'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useTeams } from '@/contexts/TeamsContext';

const TEAM_A_ID = 'team-a';

export default function AgentTeamChannel() {
  const { getTeam, getEventsForTeam } = useTeams();
  const team = getTeam(TEAM_A_ID);
  const teamEvents = getEventsForTeam(TEAM_A_ID);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title="# Team Channel"
          subtitle="Team coordination chat"
          teamName={team?.name ?? 'Team A'}
          teamMemberNames={team?.members ?? []}
          teamEvents={teamEvents}
        />
      </div>
    </div>
  );
}
