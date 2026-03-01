'use client';

import { LayoutDashboard, Store, TrendingUp, MessageSquare, Plug, Settings } from 'lucide-react';
import { SidebarBase } from './sidebar-base';

const menuItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/user/dashboard' },
  { icon: Store, label: 'Stores', path: '/user/stores' },
  { icon: TrendingUp, label: 'Analytics', path: '/user/analytics' },
  { icon: MessageSquare, label: 'Chat', path: '/user/chat' },
  { icon: Plug, label: 'Integrations', path: '/user/integrations' },
  { icon: Settings, label: 'Settings', path: '/user/settings' },
];

export function UserSidebar() {
  return <SidebarBase menuItems={menuItems} title="Arabia Dropshipping" />;
}
