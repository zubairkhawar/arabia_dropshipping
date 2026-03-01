export default function AdminKnowledgeBase() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Knowledge Base</h1>
        <p className="text-text-secondary mt-1">Manage AI knowledge base content</p>
      </div>
      
      <div className="bg-sidebar rounded-lg p-6 border border-border">
        <div className="flex items-center justify-between mb-4">
          <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm">
            Add Article
          </button>
        </div>
        <div className="text-center py-12">
          <p className="text-text-secondary">No articles in knowledge base</p>
        </div>
      </div>
    </div>
  );
}
