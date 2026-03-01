'use client';

export function ContextPanel() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-semibold text-text-primary mb-4">Customer Info</h3>
          <div className="space-y-3">
            <div>
              <p className="text-xs text-text-secondary mb-1">Name</p>
              <p className="text-sm text-text-primary">Ahmed Ali</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Phone</p>
              <p className="text-sm text-text-primary">+971 50 123 4567</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Email</p>
              <p className="text-sm text-text-primary">ahmed.ali@example.com</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Customer ID</p>
              <p className="text-sm text-text-primary">#1234</p>
            </div>
          </div>
        </div>
        
        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Store Details</h3>
          <div className="space-y-3">
            <div>
              <p className="text-xs text-text-secondary mb-1">Store Name</p>
              <p className="text-sm text-text-primary">My Shopify Store</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Store Code</p>
              <p className="text-sm text-text-primary">STORE001</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Store Type</p>
              <p className="text-sm text-text-primary">Shopify</p>
            </div>
          </div>
        </div>
        
        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Current Order</h3>
          <div className="p-3 bg-panel rounded-lg border border-border">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-text-primary">Order #12345</p>
              <span className="text-xs px-2 py-1 bg-status-warning/10 text-status-warning rounded">
                In Transit
              </span>
            </div>
            <p className="text-xs text-text-secondary mb-2">$99.99 • 3 items</p>
            <p className="text-xs text-text-muted">Placed on Jan 15, 2024</p>
            <button className="mt-3 w-full text-xs text-primary hover:text-primary-dark">
              View Full Details →
            </button>
          </div>
        </div>

        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Order History</h3>
          <div className="space-y-2">
            <div className="p-3 bg-panel rounded-lg border border-border">
              <p className="text-sm font-medium text-text-primary">Order #12344</p>
              <p className="text-xs text-text-secondary">$149.99 • Delivered</p>
            </div>
            <div className="p-3 bg-panel rounded-lg border border-border">
              <p className="text-sm font-medium text-text-primary">Order #12343</p>
              <p className="text-xs text-text-secondary">$79.99 • Delivered</p>
            </div>
          </div>
        </div>

        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Internal Notes</h3>
          <textarea
            placeholder="Add internal notes..."
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
            rows={4}
          />
          <button className="mt-2 text-xs text-primary hover:text-primary-dark">
            Save Note
          </button>
        </div>
      </div>
    </div>
  );
}
