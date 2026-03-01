'use client';

import { Inbox, Activity, User } from 'lucide-react';
import { SidebarBase } from './sidebar-base';

const menuItems = [
  { icon: Inbox, label: 'Inbox', path: '/agent/inbox' },
  { icon: Activity, label: 'Activity', path: '/agent/activity' },
  { icon: User, label: 'Profile', path: '/agent/profile' },
];

export function AgentSidebar() {
  return <SidebarBase menuItems={menuItems} title="Arabia Dropshipping" />;
}
