import { useState } from "react";

export default function EngagementRatePanel() {
  const [totalInteractions, setTotalInteractions] = useState(0);
  const [totalViews, setTotalViews] = useState(0);
  const [result, setResult] = useState(null);

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/engagement_rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        total_interactions: parseFloat(totalInteractions),
        total_views: parseFloat(totalViews)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#9b59b6" }}>Engagement Rate</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Interactions</label><input type="number" style={inputStyle} value={totalInteractions} onChange={(e)=>setTotalInteractions(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Total Views</label><input type="number" style={inputStyle} value={totalViews} onChange={(e)=>setTotalViews(e.target.value)} /></div>
      </div>
      <button style={{ backgroundColor: "#9b59b6", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Calculate Rate</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #331a4d" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#9b59b6" }}>{val}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}