'use client';

import { KPICard } from '@/components/cards/kpi-card';
import { LineChartComponent } from '@/components/charts/line-chart';
import { BarChartComponent } from '@/components/charts/bar-chart';

export default function UserDashboard() {
  const orderData = [
    { name: 'Mon', orders: 12 },
    { name: 'Tue', orders: 19 },
    { name: 'Wed', orders: 15 },
    { name: 'Thu', orders: 25 },
    { name: 'Fri', orders: 22 },
    { name: 'Sat', orders: 30 },
    { name: 'Sun', orders: 28 },
  ];

  const revenueData = [
    { name: 'Week 1', revenue: 4500 },
    { name: 'Week 2', revenue: 5200 },
    { name: 'Week 3', revenue: 4800 },
    { name: 'Week 4', revenue: 6100 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-text-secondary mt-1">Welcome to your store analytics</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard 
          title="Total Orders" 
          value="1,234" 
          change="+12.5%"
          changeType="positive"
          icon="📦"
        />
        <KPICard 
          title="Delivered" 
          value="1,089" 
          change="+8.2%"
          changeType="positive"
          icon="✅"
        />
        <KPICard 
          title="In Transit" 
          value="98" 
          change="-3.1%"
          changeType="negative"
          icon="🚚"
        />
        <KPICard 
          title="Revenue" 
          value="$52,340" 
          change="+15.3%"
          changeType="positive"
          icon="💰"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Orders Trend</h3>
          <LineChartComponent data={orderData} dataKey="orders" height={280} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Revenue Trend</h3>
          <BarChartComponent data={revenueData} dataKey="revenue" height={280} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Order Status</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Pending</span>
              <span className="text-sm font-medium text-text-primary">47</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Dispatched</span>
              <span className="text-sm font-medium text-text-primary">23</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">In Transit</span>
              <span className="text-sm font-medium text-text-primary">98</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Delivered</span>
              <span className="text-sm font-medium text-status-success">1,089</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Returned</span>
              <span className="text-sm font-medium text-status-error">12</span>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Top Products</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Product A</span>
              <span className="text-sm font-medium text-text-primary">234 orders</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Product B</span>
              <span className="text-sm font-medium text-text-primary">189 orders</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Product C</span>
              <span className="text-sm font-medium text-text-primary">156 orders</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Product D</span>
              <span className="text-sm font-medium text-text-primary">142 orders</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Product E</span>
              <span className="text-sm font-medium text-text-primary">98 orders</span>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Recent Activity</h3>
          </div>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-text-primary">New order #12345</p>
              <p className="text-xs text-text-muted">2 minutes ago</p>
            </div>
            <div>
              <p className="text-sm text-text-primary">Order #12344 delivered</p>
              <p className="text-xs text-text-muted">15 minutes ago</p>
            </div>
            <div>
              <p className="text-sm text-text-primary">New customer registered</p>
              <p className="text-xs text-text-muted">1 hour ago</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
