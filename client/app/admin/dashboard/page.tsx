'use client';

import { KPICard } from '@/components/cards/kpi-card';
import { LineChartComponent } from '@/components/charts/line-chart';
import { BarChartComponent } from '@/components/charts/bar-chart';

export default function AdminDashboard() {
  const agentActivity = [
    { name: 'Mon', active: 12, busy: 3 },
    { name: 'Tue', active: 15, busy: 2 },
    { name: 'Wed', active: 14, busy: 4 },
    { name: 'Thu', active: 18, busy: 3 },
    { name: 'Fri', active: 16, busy: 2 },
    { name: 'Sat', active: 10, busy: 1 },
    { name: 'Sun', active: 8, busy: 1 },
  ];

  const conversationStats = [
    { name: 'Week 1', total: 450, resolved: 420 },
    { name: 'Week 2', total: 520, resolved: 495 },
    { name: 'Week 3', total: 480, resolved: 460 },
    { name: 'Week 4', total: 610, resolved: 585 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Admin Dashboard</h1>
        <p className="text-text-secondary mt-1">System overview and monitoring</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard 
          title="Total Tenants" 
          value="24" 
          change="+3 this month"
          changeType="positive"
          icon="🏢"
        />
        <KPICard 
          title="Active Agents" 
          value="18" 
          change="+2 today"
          changeType="positive"
          icon="👥"
        />
        <KPICard 
          title="Active Conversations" 
          value="142" 
          change="+12 today"
          changeType="positive"
          icon="💬"
        />
        <KPICard 
          title="AI Response Rate" 
          value="87.5%" 
          change="+2.3%"
          changeType="positive"
          icon="🤖"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Agent Activity</h3>
          <LineChartComponent data={agentActivity} dataKey="active" height={280} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Conversation Statistics</h3>
          <BarChartComponent data={conversationStats} dataKey="total" height={280} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">System Health</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">API Status</span>
              <span className="text-sm font-medium text-status-success">Healthy</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Database</span>
              <span className="text-sm font-medium text-status-success">Connected</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Redis Cache</span>
              <span className="text-sm font-medium text-status-success">Active</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">AI Service</span>
              <span className="text-sm font-medium text-status-success">Operational</span>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Recent Activity</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-text-primary">New tenant registered</p>
              <p className="text-xs text-text-muted">5 minutes ago</p>
            </div>
            <div>
              <p className="text-sm text-text-primary">Agent status changed</p>
              <p className="text-xs text-text-muted">12 minutes ago</p>
            </div>
            <div>
              <p className="text-sm text-text-primary">System backup completed</p>
              <p className="text-xs text-text-muted">1 hour ago</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Performance Metrics</h3>
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-text-secondary">Avg Response Time</span>
                <span className="text-sm font-medium text-text-primary">1.2s</span>
              </div>
              <div className="w-full bg-panel rounded-full h-2">
                <div className="bg-status-success h-2 rounded-full" style={{ width: '85%' }}></div>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-text-secondary">Uptime</span>
                <span className="text-sm font-medium text-text-primary">99.9%</span>
              </div>
              <div className="w-full bg-panel rounded-full h-2">
                <div className="bg-status-success h-2 rounded-full" style={{ width: '99%' }}></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
