'use client';

import { LineChartComponent } from '@/components/charts/line-chart';
import { BarChartComponent } from '@/components/charts/bar-chart';
import { PieChartComponent } from '@/components/charts/pie-chart';

export default function AdminAnalytics() {
  const aiPerformance = [
    { name: 'Mon', accuracy: 85, responses: 120 },
    { name: 'Tue', accuracy: 87, responses: 135 },
    { name: 'Wed', accuracy: 89, responses: 142 },
    { name: 'Thu', accuracy: 88, responses: 138 },
    { name: 'Fri', accuracy: 90, responses: 145 },
    { name: 'Sat', accuracy: 87, responses: 98 },
    { name: 'Sun', accuracy: 86, responses: 85 },
  ];

  const agentActivity = [
    { name: 'Mon', chats: 450, resolved: 420 },
    { name: 'Tue', chats: 520, resolved: 495 },
    { name: 'Wed', chats: 480, resolved: 460 },
    { name: 'Thu', chats: 610, resolved: 585 },
  ];

  const languageDistribution = [
    { name: 'Arabic', value: 45 },
    { name: 'English', value: 35 },
    { name: 'Roman Urdu', value: 20 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">System Analytics</h1>
        <p className="text-text-secondary mt-1">Platform-wide performance metrics</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">AI Performance</h3>
          <LineChartComponent data={aiPerformance} dataKey="accuracy" height={320} strokeColor="#22C55E" />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Agent Activity</h3>
          <BarChartComponent data={agentActivity} dataKey="chats" height={320} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm lg:col-span-2">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Language Distribution</h3>
          <PieChartComponent data={languageDistribution} height={360} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <p className="text-sm text-text-secondary mb-2">Total Messages</p>
          <p className="text-2xl font-bold text-text-primary">45,234</p>
          <p className="text-xs text-text-muted mt-1">+12.5% from last week</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">AI Handled</p>
          <p className="text-2xl font-bold text-text-primary">38,456</p>
          <p className="text-xs text-text-muted mt-1">85% of total</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">Agent Escalations</p>
          <p className="text-2xl font-bold text-text-primary">6,778</p>
          <p className="text-xs text-text-muted mt-1">15% escalation rate</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">Avg Resolution Time</p>
          <p className="text-2xl font-bold text-text-primary">4.2m</p>
          <p className="text-xs text-text-muted mt-1">-0.8m from last week</p>
        </div>
      </div>
    </div>
  );
}
