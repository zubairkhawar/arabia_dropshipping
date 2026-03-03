'use client';

import { MessageCircle } from 'lucide-react';

export default function DmHubPage() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 bg-scaffold text-center p-8">
      <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-4">
        <MessageCircle className="w-8 h-8" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary mb-1">Direct Messages</h2>
      <p className="text-sm text-text-muted max-w-xs">
        Select a conversation from the list or start a new chat with an agent using the button below.
      </p>
    </div>
  );
}
