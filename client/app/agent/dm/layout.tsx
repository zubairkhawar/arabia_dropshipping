'use client';

import { DmMiddleBar } from '@/components/dm/dm-middle-bar';
import { DmLayoutProvider } from '@/contexts/DmLayoutContext';

export default function DmLayout({ children }: { children: React.ReactNode }) {
  return (
    <DmLayoutProvider>
      <div className="flex h-full min-h-0">
        <DmMiddleBar />
        <div className="flex-1 min-w-0 flex flex-col">{children}</div>
      </div>
    </DmLayoutProvider>
  );
}
