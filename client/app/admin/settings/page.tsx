export default function AdminSettings() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-text-secondary mt-1">System configuration and preferences</p>
      </div>
      
      <div className="bg-sidebar rounded-lg p-6 border border-border space-y-6">
        <div>
          <h3 className="font-semibold text-text-primary mb-4">System Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">Platform Name</label>
              <input
                type="text"
                className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                defaultValue="Arabia Dropshipping"
              />
            </div>
          </div>
        </div>
        
        <div className="border-t border-border pt-6">
          <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors">
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
