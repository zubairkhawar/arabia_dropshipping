export default function AgentProfile() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Profile</h1>
        <p className="text-text-secondary mt-1">Manage your agent profile and settings</p>
      </div>
      
      <div className="bg-sidebar rounded-lg p-6 border border-border space-y-6">
        <div>
          <h3 className="font-semibold text-text-primary mb-4">Status</h3>
          <div className="flex items-center gap-4">
            <button className="px-4 py-2 bg-status-success text-white rounded-lg text-sm">
              Online
            </button>
            <button className="px-4 py-2 bg-status-warning text-white rounded-lg text-sm">
              Busy
            </button>
            <button className="px-4 py-2 bg-text-muted text-white rounded-lg text-sm">
              Offline
            </button>
          </div>
        </div>
        
        <div className="border-t border-border pt-6">
          <h3 className="font-semibold text-text-primary mb-4">Profile Information</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">Full Name</label>
              <input
                type="text"
                className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Enter your name"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
