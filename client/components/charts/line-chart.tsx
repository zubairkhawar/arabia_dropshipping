'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface LineChartProps {
  data: Array<Record<string, any>>;
  dataKey: string;
  strokeColor?: string;
  height?: number;
}

export function LineChartComponent({ data, dataKey, strokeColor = '#1158A4', height = 300 }: LineChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
        <XAxis dataKey="name" stroke="#94A3B8" />
        <YAxis stroke="#94A3B8" />
        <Tooltip 
          contentStyle={{ 
            backgroundColor: '#FFFFFF', 
            border: '1px solid #E5E7EB',
            borderRadius: '8px'
          }} 
        />
        <Legend />
        <Line 
          type="monotone" 
          dataKey={dataKey} 
          stroke={strokeColor} 
          strokeWidth={2}
          dot={{ fill: strokeColor, r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
