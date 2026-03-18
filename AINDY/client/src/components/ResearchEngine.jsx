import React, { useState } from "react";
import { runResearch } from "../api";

export default function ResearchEngine() {
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const data = await runResearch(query, summary);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-lg mx-auto text-white">
      <h1 className="text-2xl font-bold mb-4">A.I.N.D.Y. Research Engine</h1>
      
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col">
          <label className="text-sm text-gray-400 mb-1">Research Query</label>
          <input
            type="text"
            placeholder="Enter your research query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
            className="bg-zinc-900 border border-zinc-700 text-white rounded p-3 outline-none focus:border-blue-500 transition-colors"
          />
        </div>

        <div className="flex flex-col">
          <label className="text-sm text-gray-400 mb-1">Context / Summary (Optional)</label>
          <textarea
            placeholder="Provide additional context..."
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows="4"
            className="bg-zinc-900 border border-zinc-700 text-white rounded p-3 outline-none focus:border-blue-500 transition-colors"
          />
        </div>

        <button
          type="submit"
          className="bg-blue-600 hover:bg-blue-700 text-white font-bold rounded p-3 transition-colors disabled:bg-gray-600"
          disabled={loading}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Processing...
            </span>
          ) : "Run Research"}
        </button>
      </form>

      {error && (
        <div className="bg-red-900/30 border border-red-600 text-red-200 p-3 rounded mt-4">
          {error}
        </div>
      )}

      {result && (
        <div className="border border-zinc-700 rounded p-5 mt-6 bg-zinc-900 shadow-xl">
          <h2 className="font-semibold text-xl mb-2 text-blue-400 border-b border-zinc-800 pb-2">
            Research Results
          </h2>
          <div className="space-y-3">
            <p className="text-sm">
              <span className="text-gray-500 uppercase text-xs block font-bold">Query</span>
              {result.query}
            </p>
            <p className="text-sm leading-relaxed">
              <span className="text-gray-500 uppercase text-xs block font-bold">Analysis</span>
              {result.summary}
            </p>
            <div className="text-[10px] text-gray-500 pt-4 flex justify-between">
              <span>A.I.N.D.Y. Engine v1.0</span>
              <span>{new Date(result.created_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}