import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { ContextPanel } from '@/components/chat/context-panel';

export default function AgentInbox() {
  return (
    <div className="flex h-full">
      <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-panel">
        <ChatList />
      </div>
      <div className="flex-1 flex flex-col">
        <ChatWindow />
      </div>
      <div className="hidden lg:block w-context-laptop xl:w-context-desktop 2xl:w-context-ultrawide border-l border-border bg-panel">
        <ContextPanel />
      </div>
    </div>
  );
}
