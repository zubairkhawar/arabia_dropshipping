'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { DmMiddleBar } from '@/components/dm/dm-middle-bar';
import { DmLayoutProvider } from '@/contexts/DmLayoutContext';

export default function DmLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const hasSlug = pathname.startsWith('/agent/dm/');
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 425px)');
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);

  // Mobile push/pop: list when no slug, conversation when slug.
  const showMiddleBar = !isMobile || !hasSlug;
  const showContent = !isMobile || hasSlug;

  return (
    <DmLayoutProvider>
      <div className="flex h-full min-h-0">
        {showMiddleBar && (
          <div className={isMobile ? 'flex-1 min-w-0 flex' : 'flex'}>
            <DmMiddleBar />
          </div>
        )}
        {showContent && <div className="flex-1 min-w-0 flex flex-col">{children}</div>}
      </div>
    </DmLayoutProvider>
  );
}
