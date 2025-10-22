import React, { useState } from 'react';

export default function ResearchEngine() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("http://localhost:8000/research/query", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ query })
      });

      if (!res.ok) throw new Error("Server error");
      const data = await res.json();
      setResult(data.summary || "No summary returned.");
    } catch (err) {
      setError("Could not reach A.I.N.D.Y. backend. Check if it’s running.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-xl mx-auto">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your research topic"
          className="p-2 border rounded"
        />
        <button
          type="submit"
          disabled={loading}
          className="p-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          {loading ? "Running..." : "Run Research"}
        </button>
      </form>

      {error && <p className="mt-2 text-red-600">{error}</p>}

      {result && (
        <div className="mt-4 p-3 border rounded bg-gray-50">
          <h2 className="font-bold text-lg mb-2">Summary</h2>
          <p>{result}</p>
        </div>
      )}
    </div>
  );
}
