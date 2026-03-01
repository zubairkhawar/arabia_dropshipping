'use client';

import { useState } from 'react';

export default function UserStores() {
  const [stores] = useState([
    {
      id: 1,
      name: 'My Shopify Store',
      storeCode: 'STORE001',
      type: 'Shopify',
      status: 'active',
      orders: 1234,
      revenue: '$52,340',
      lastSync: '2 minutes ago',
    },
    {
      id: 2,
      name: 'WooCommerce Shop',
      storeCode: 'STORE002',
      type: 'WooCommerce',
      status: 'active',
      orders: 856,
      revenue: '$38,920',
      lastSync: '5 minutes ago',
    },
  ]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Stores</h1>
          <p className="text-text-secondary mt-1">Manage your ecommerce store integrations</p>
        </div>
        <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors">
          + Add Store
        </button>
      </div>
      
      {stores.length === 0 ? (
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <div className="text-center py-12">
            <p className="text-text-secondary mb-4">No stores connected yet</p>
            <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors">
              Add Store
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {stores.map((store) => (
            <div key={store.id} className="bg-white rounded-lg p-6 border border-border shadow-sm">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">{store.name}</h3>
                  <p className="text-sm text-text-secondary mt-1">Code: {store.storeCode}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    store.status === 'active' 
                      ? 'bg-status-success/10 text-status-success' 
                      : 'bg-text-muted/10 text-text-muted'
                  }`}>
                    {store.status}
                  </span>
                  <span className="px-2 py-1 rounded text-xs bg-primary/10 text-primary">
                    {store.type}
                  </span>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-xs text-text-secondary mb-1">Total Orders</p>
                  <p className="text-lg font-semibold text-text-primary">{store.orders.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary mb-1">Revenue</p>
                  <p className="text-lg font-semibold text-text-primary">{store.revenue}</p>
                </div>
              </div>
              
              <div className="flex items-center justify-between pt-4 border-t border-border">
                <p className="text-xs text-text-muted">Last synced: {store.lastSync}</p>
                <div className="flex items-center gap-2">
                  <button className="text-sm text-primary hover:text-primary-dark">
                    Sync Now
                  </button>
                  <button className="text-sm text-text-secondary hover:text-text-primary">
                    Settings
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
