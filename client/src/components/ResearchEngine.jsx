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
    <div className="p-6 max-w-lg mx-auto">
      <h1 className="text-2xl font-bold mb-4">A.I.N.D.Y. Research Engine</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="text"
          placeholder="Enter your research query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          required
          className="border rounded p-2"
        />
        <textarea
          placeholder="Optional summary or context"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows="3"
          className="border rounded p-2"
        />
        <button
          type="submit"
          className="bg-blue-600 text-white rounded p-2"
          disabled={loading}
        >
          {loading ? "Running..." : "Run Research"}
        </button>
      </form>

      {error && <p className="text-red-600 mt-2">{error}</p>}

      {result && (
        <div className="border rounded p-4 mt-4 bg-gray-50">
          <h2 className="font-semibold text-lg mb-1">{result.query}</h2>
          <p className="text-sm text-gray-700">{result.summary}</p>
          <p className="text-xs text-gray-500 mt-2">
            Logged at: {new Date(result.created_at).toLocaleString()}
          </p>
        </div>
      )}
    </div>
  );
}

