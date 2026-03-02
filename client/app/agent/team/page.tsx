'use client';

import { ChatWindow } from '@/components/chat/chat-window';

const TEAM_MEMBERS = ['Ali', 'Hamza', 'Sarah'];

export default function AgentTeamChannel() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title="# Team Channel"
          subtitle="Team coordination chat"
          teamName="Team A"
          teamMemberNames={TEAM_MEMBERS}
        />
      </div>
    </div>
  );
}
