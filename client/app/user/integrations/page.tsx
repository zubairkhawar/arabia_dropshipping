export default function UserIntegrations() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Integrations</h1>
        <p className="text-text-secondary mt-1">Connect your ecommerce platforms</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <h3 className="font-semibold text-text-primary mb-2">Shopify</h3>
          <p className="text-sm text-text-secondary mb-4">Connect your Shopify store</p>
          <button className="w-full bg-primary text-white py-2 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm">
            Connect
          </button>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <h3 className="font-semibold text-text-primary mb-2">WooCommerce</h3>
          <p className="text-sm text-text-secondary mb-4">Connect your WooCommerce store</p>
          <button className="w-full bg-primary text-white py-2 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm">
            Connect
          </button>
        </div>
        <div className="bg-sidebar rounded-lg p-6 border border-border">
          <h3 className="font-semibold text-text-primary mb-2">Custom API</h3>
          <p className="text-sm text-text-secondary mb-4">Connect via custom API</p>
          <button className="w-full bg-primary text-white py-2 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm">
            Connect
          </button>
        </div>
      </div>
    </div>
  );
}
