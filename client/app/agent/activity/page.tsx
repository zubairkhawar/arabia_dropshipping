export default function AgentActivity() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Activity</h1>
        <p className="text-text-secondary mt-1">Your conversation history and statistics</p>
      </div>
      
      <div className="bg-sidebar rounded-lg p-6 border border-border">
        <div className="text-center py-12">
          <p className="text-text-secondary">No activity yet</p>
        </div>
      </div>
    </div>
  );
}
