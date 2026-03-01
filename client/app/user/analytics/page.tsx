'use client';

import { LineChartComponent } from '@/components/charts/line-chart';
import { BarChartComponent } from '@/components/charts/bar-chart';
import { PieChartComponent } from '@/components/charts/pie-chart';

export default function UserAnalytics() {
  const orderTrends = [
    { name: 'Jan', orders: 120 },
    { name: 'Feb', orders: 145 },
    { name: 'Mar', orders: 132 },
    { name: 'Apr', orders: 168 },
    { name: 'May', orders: 189 },
    { name: 'Jun', orders: 201 },
  ];

  const revenueData = [
    { name: 'Jan', revenue: 12000 },
    { name: 'Feb', revenue: 14500 },
    { name: 'Mar', revenue: 13200 },
    { name: 'Apr', revenue: 16800 },
    { name: 'May', revenue: 18900 },
    { name: 'Jun', revenue: 20100 },
  ];

  const statusDistribution = [
    { name: 'Delivered', value: 1089 },
    { name: 'In Transit', value: 98 },
    { name: 'Pending', value: 47 },
    { name: 'Returned', value: 12 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Analytics</h1>
        <p className="text-text-secondary mt-1">Store performance and insights</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Order Trends</h3>
          <LineChartComponent data={orderTrends} dataKey="orders" height={320} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Revenue Analysis</h3>
          <BarChartComponent data={revenueData} dataKey="revenue" height={320} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm lg:col-span-2">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Order Status Distribution</h3>
          <PieChartComponent data={statusDistribution} height={360} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <p className="text-sm text-text-secondary mb-2">Average Order Value</p>
          <p className="text-2xl font-bold text-text-primary">$42.50</p>
          <p className="text-xs text-text-muted mt-1">+5.2% from last month</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">Conversion Rate</p>
          <p className="text-2xl font-bold text-text-primary">3.2%</p>
          <p className="text-xs text-text-muted mt-1">+0.8% from last month</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">Customer Lifetime Value</p>
          <p className="text-2xl font-bold text-text-primary">$127</p>
          <p className="text-xs text-text-muted mt-1">+12.1% from last month</p>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <p className="text-sm text-text-secondary mb-2">Return Rate</p>
          <p className="text-2xl font-bold text-status-error">1.2%</p>
          <p className="text-xs text-text-muted mt-1">-0.3% from last month</p>
        </div>
      </div>
    </div>
  );
}
