'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useParams } from 'next/navigation';
import { useDmChats } from '@/contexts/DmChatsContext';
import { useEffect } from 'react';
import { AGENTS_BY_TEAM } from '@/contexts/AgentPresenceContext';

function getNameForSlug(slug: string): string {
  for (const { members } of AGENTS_BY_TEAM) {
    const m = members.find((x) => x.slug === slug);
    if (m) return m.name;
  }
  return slug.charAt(0).toUpperCase() + slug.slice(1);
}

export default function AgentDMPage() {
  const params = useParams();
  const slug = (params?.slug as string) || 'ali';
  const name = getNameForSlug(slug);
  const { addOrUpdateConversation } = useDmChats();

  useEffect(() => {
    addOrUpdateConversation(slug, name);
  }, [slug, name, addOrUpdateConversation]);

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
