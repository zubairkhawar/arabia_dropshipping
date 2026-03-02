'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useParams } from 'next/navigation';

export default function AgentTeamChannel() {
  const params = useParams();
  const channel = (params?.channel as string) || 'team';

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title={`# ${channel === 'team' ? 'Team Channel' : channel}`}
          subtitle="Team coordination chat"
        />
      </div>
    </div>
  );
}
