export default function AdminTenants() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Tenants</h1>
        <p className="text-text-secondary mt-1">Manage platform tenants</p>
      </div>
      
      <div className="bg-sidebar rounded-lg p-6 border border-border">
        <div className="flex items-center justify-between mb-4">
          <input
            type="text"
            placeholder="Search tenants..."
            className="px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
          />
          <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm">
            Add Tenant
          </button>
        </div>
        <div className="text-center py-12">
          <p className="text-text-secondary">No tenants found</p>
        </div>
      </div>
    </div>
  );
}
