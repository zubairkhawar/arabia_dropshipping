'use client';

import { ChatWindow } from '@/components/chat/chat-window';
import { useParams } from 'next/navigation';

export default function AgentDMPage() {
  const params = useParams();
  const slug = (params?.slug as string) || 'ali';
  const name = slug.charAt(0).toUpperCase() + slug.slice(1);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ChatWindow
          isInternalChat
          title={`@ ${name}`}
          subtitle="Direct message"
        />
      </div>
    </div>
  );
}
