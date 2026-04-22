import { useEffect, useState } from "react";
import { deleteSearchHistoryItem, getSearchHistory } from "../../api";

export default function SearchHistory({ searchType = null, title = "Search History", onSelect }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadHistory() {
    setLoading(true);
    setError("");
    try {
      const response = await getSearchHistory(searchType, 12);
      setItems(response.items || []);
    } catch (err) {
      setError(err.message || "Failed to load search history");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(historyId) {
    try {
      await deleteSearchHistoryItem(historyId);
      setItems((current) => current.filter((item) => item.id !== historyId));
    } catch (err) {
      setError(err.message || "Failed to delete search history");
    }
  }

  useEffect(() => {
    loadHistory();
  }, [searchType]);

  return (
    <div className="border border-zinc-800 rounded-lg bg-zinc-950/70 p-4 mt-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
          <p className="text-xs text-zinc-500">Recent queries and reusable results</p>
        </div>
        <button
          type="button"
          onClick={loadHistory}
          className="text-xs text-blue-400 hover:text-blue-300"
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <div className="text-xs text-red-400 mb-3">{error}</div>}
      {!loading && items.length === 0 && (
        <div className="text-xs text-zinc-500">No saved searches yet.</div>
      )}

      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id} className="border border-zinc-800 rounded-md p-3 bg-zinc-900/70">
            <div className="flex items-start justify-between gap-3">
              <button
                type="button"
                onClick={() => onSelect?.(item)}
                className="text-left flex-1"
              >
                <div className="text-sm text-zinc-100">{item.query}</div>
                <div className="text-[11px] text-zinc-500 mt-1">
                  {(item.search_type || "search").replace(/_/g, " ")} ·{" "}
                  {item.created_at ? new Date(item.created_at).toLocaleString() : "unknown time"}
                </div>
              </button>
              <button
                type="button"
                onClick={() => handleDelete(item.id)}
                className="text-xs text-red-400 hover:text-red-300"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
