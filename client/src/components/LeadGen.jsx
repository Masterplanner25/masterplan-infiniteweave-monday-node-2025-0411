import { useState } from "react";
import { runLeadGen } from "../api";

export default function LeadGen() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);

  async function handleLeadGen() {
    if (!query.trim()) return;

    setLoading(true);
    try {
      const response = await runLeadGen(query);
      setResults(response.leads || []);
    } catch (err) {
      console.error("LeadGen error:", err);
    }
    setLoading(false);
  }

  return (
    <div className="page-container">
      <h1 className="page-title">AI Lead Generation</h1>

      <div className="input-section">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ex: 'hiring AI consultants'"
          className="text-input"
        />
        <button onClick={handleLeadGen} className="primary-button">
          {loading ? "Searching..." : "Run LeadGen"}
        </button>
      </div>

      <div className="results-section">
        {results.length === 0 && !loading && (
          <p className="empty-text">No leads yet — run a search above.</p>
        )}

        {results.map((lead, i) => (
          <div key={i} className="lead-card">
            <h3>{lead.company}</h3>
            <p>{lead.reason}</p>
            <div className="lead-score">Score: {lead.score}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
