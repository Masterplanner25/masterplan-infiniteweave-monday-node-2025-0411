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
    <div className="page-container" style={{ padding: '20px', maxWidth: '800px', margin: '0 auto', color: '#fff' }}>
      {/* Internal CSS to fix the visibility issues immediately */}
      <style>{`
        .page-title { color: #fff; font-size: 24px; font-weight: bold; margin-bottom: 20px; }
        .input-section { display: flex; gap: 10px; margin-bottom: 30px; }
        
        .text-input { 
          flex: 1; 
          padding: 12px; 
          background: #1a1a1a; 
          border: 1px solid #333; 
          color: #fff; 
          border-radius: 6px;
          outline: none;
        }
        .text-input:focus { border-color: #007bff; }

        .primary-button { 
          padding: 12px 24px; 
          background: #007bff; 
          color: #fff; 
          border: none; 
          border-radius: 6px; 
          cursor: pointer; 
          font-weight: bold;
        }
        .primary-button:disabled { background: #333; cursor: not-allowed; }

        .lead-card { 
          background: #141414; 
          border: 1px solid #222; 
          padding: 20px; 
          border-radius: 8px; 
          margin-bottom: 15px; 
        }
        .lead-card h3 { margin: 0 0 10px 0; color: #4dabf7; }
        .lead-card p { color: #ccc; font-size: 14px; line-height: 1.5; }
        
        .lead-score { 
          display: inline-block; 
          margin-top: 10px; 
          padding: 4px 8px; 
          background: #2b2f33; 
          border-radius: 4px; 
          font-size: 12px; 
          color: #ffda5f; 
          font-weight: bold;
        }
        .empty-text { color: #666; font-style: italic; }
      `}</style>

      <h1 className="page-title">AI Lead Generation</h1>

      <div className="input-section">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ex: 'hiring AI consultants'"
          className="text-input"
        />
        <button 
          onClick={handleLeadGen} 
          className="primary-button"
          disabled={loading}
        >
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
            <div className="lead-score">Match Score: {lead.score}</div>
          </div>
        ))}
      </div>
    </div>
  );
}