import { useState } from "react";

export default function AnalyticsPanel() {
  const [masterplanId, setMasterplanId] = useState("");
  const [impressions, setImpressions] = useState(0);
  const [reach, setReach] = useState(0);
  const [interactions, setInteractions] = useState(0);
  const [followers, setFollowers] = useState(0);
  
  // New Date States
  const [periodStart, setPeriodStart] = useState("2026-02-10");
  const [periodEnd, setPeriodEnd] = useState("2026-02-16");
  
  const [summary, setSummary] = useState(null);

  // --- Styles ---
  const panelStyle = { 
    backgroundColor: "#141414", 
    padding: "20px", 
    borderRadius: "12px", 
    border: "1px solid #222", 
    marginBottom: "20px" 
  };
  
  const inputStyle = { 
    backgroundColor: "#222", 
    color: "#fff", 
    border: "1px solid #444", 
    padding: "10px", 
    borderRadius: "6px", 
    width: "100%", 
    boxSizing: "border-box",
    fontSize: "14px"
  };
  
  const labelStyle = { 
    fontSize: "11px", 
    color: "#888", 
    display: "block", 
    marginBottom: "4px",
    textTransform: "uppercase",
    letterSpacing: "0.5px"
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch("http://localhost:8000/analytics/linkedin/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          masterplan_id: parseInt(masterplanId),
          platform: "linkedin",
          period_type: "weekly",
          period_start: periodStart,
          period_end: periodEnd,
          impressions: parseInt(impressions),
          reach: parseInt(reach),
          interactions: parseInt(interactions),
          followers: parseInt(followers)
        })
      });
      if (response.ok) alert("Metrics Synchronized");
    } catch (err) {
      console.error("Submission error:", err);
    }
  };

  const fetchSummary = async () => {
    if (!masterplanId) return alert("Enter a MasterPlan ID first");
    try {
      const res = await fetch(
        `http://localhost:8000/analytics/summary?masterplan_id=${masterplanId}&platform=linkedin&period_type=weekly`
      );
      const data = await res.json();
      setSummary(data);
    } catch (err) {
      console.error("Fetch error:", err);
    }
  };

  return (
    <div style={panelStyle}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h3 style={{ margin: 0, fontSize: "18px", color: "#00a2ff" }}>LinkedIn Analytics</h3>
        <span style={{ fontSize: "10px", color: "#555", background: "#222", padding: "2px 8px", borderRadius: "10px" }}>DYNAMIC TRACKING</span>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "15px", marginBottom: "15px" }}>
        <div>
          <label style={labelStyle}>MasterPlan ID</label>
          <input style={inputStyle} placeholder="ID" value={masterplanId} onChange={(e) => setMasterplanId(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Start Date</label>
          <input style={inputStyle} type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>End Date</label>
          <input style={inputStyle} type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "15px", marginBottom: "20px" }}>
        <div><label style={labelStyle}>Impressions</label><input style={inputStyle} type="number" value={impressions} onChange={(e) => setImpressions(e.target.value)} /></div>
        <div><label style={labelStyle}>Reach</label><input style={inputStyle} type="number" value={reach} onChange={(e) => setReach(e.target.value)} /></div>
        <div><label style={labelStyle}>Interactions</label><input style={inputStyle} type="number" value={interactions} onChange={(e) => setInteractions(e.target.value)} /></div>
        <div><label style={labelStyle}>Followers</label><input style={inputStyle} type="number" value={followers} onChange={(e) => setFollowers(e.target.value)} /></div>
      </div>

      <div style={{ display: "flex", gap: "10px" }}>
        <button onClick={handleSubmit} style={{ flex: 1, backgroundColor: "#007bff", color: "#fff", border: "none", padding: "12px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>Submit Metrics</button>
        <button onClick={fetchSummary} style={{ flex: 1, backgroundColor: "transparent", color: "#00ffaa", border: "1px solid #00ffaa", padding: "12px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>Fetch Summary</button>
      </div>

      {summary && (
        <div style={{ marginTop: "20px", padding: "15px", backgroundColor: "#0a0a0a", borderRadius: "8px", border: "1px solid #333" }}>
          <h4 style={{ margin: "0 0 10px 0", fontSize: "12px", color: "#888" }}>ANALYTICS SUMMARY</h4>
          <pre style={{ color: "#00ffaa", fontSize: "12px", whiteSpace: "pre-wrap", margin: 0, fontFamily: "monospace" }}>
            {JSON.stringify(summary, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}