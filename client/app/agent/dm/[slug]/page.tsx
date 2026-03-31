'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useParams } from 'next/navigation';
import { useDmChats } from '@/contexts/DmChatsContext';
import { useEffect } from 'react';
import { useAgentPresence } from '@/contexts/AgentPresenceContext';

export default function AgentDMPage() {
  const params = useParams();
  const slug = (params?.slug as string) || 'ali';
  const { agentsByTeam } = useAgentPresence();
  const match = agentsByTeam
    .flatMap((group) => group.members)
    .find((member) => member.slug === slug);
  const name = match?.name || slug.charAt(0).toUpperCase() + slug.slice(1);
  const { addOrUpdateConversation } = useDmChats();

  useEffect(() => {
    if (!match?.agentId) return;
    void addOrUpdateConversation(match.agentId, slug, name);
  }, [slug, name, match?.agentId, addOrUpdateConversation]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title={name}
          subtitle="Direct message"
        />
      </div>
    </div>
  );
}
