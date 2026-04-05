'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { MessageCircle, MessageSquarePlus } from 'lucide-react';
import { useDmChats } from '@/contexts/DmChatsContext';
import { useDmLayout } from '@/contexts/DmLayoutContext';

export default function DmHubPage() {
  const router = useRouter();
  const { conversations, isDmListLoading } = useDmChats();
  const { toggleMiddleBar, middleBarCollapsed } = useDmLayout();

  useEffect(() => {
    if (isDmListLoading) return;
    if (conversations.length === 0) return;
    const sorted = [...conversations].sort(
      (a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime(),
    );
    const first = sorted[0];
    if (first?.slug) {
      router.replace(`/agent/dm/${first.slug}`);
    }
  }, [isDmListLoading, conversations, router]);

  if (isDmListLoading || conversations.length > 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 bg-scaffold p-8 min-h-[200px]">
        <div
          className="h-10 w-10 rounded-full border-2 border-primary border-t-transparent animate-spin"
          aria-hidden
        />
        <p className="mt-4 text-sm text-text-muted">
          {isDmListLoading ? 'Loading conversations…' : 'Opening your latest chat…'}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center flex-1 bg-scaffold text-center p-8 min-h-[200px]">
      <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-4">
        <MessageCircle className="w-8 h-8" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary mb-1">Direct Messages</h2>
      <p className="text-sm text-text-muted max-w-sm mb-6">
        You do not have any conversations yet. Start a new chat with a teammate from the list on the left.
      </p>
      <button
        type="button"
        onClick={() => {
          if (middleBarCollapsed) toggleMiddleBar();
        }}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
      >
        <MessageSquarePlus className="w-5 h-5" />
        Start a new chat
      </button>
      <p className="mt-4 text-xs text-text-muted">
        Tip: use the <span className="font-medium text-text-secondary">+</span> button in the conversation list
        to pick an agent.
      </p>
      <Link
        href="/agent/inbox"
        className="mt-6 text-sm text-primary hover:underline"
      >
        Back to My Chats
      </Link>
    </div>
  );
}
