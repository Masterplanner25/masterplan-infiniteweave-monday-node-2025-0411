import { useState } from "react";

export default function LostPotentialPanel() {
  const [missedOpportunities, setMissedOpportunities] = useState(0);
  const [timeDelayed, setTimeDelayed] = useState(0);
  const [gainsFromAction, setGainsFromAction] = useState(0);
  const [result, setResult] = useState(null);

  const formatCurrency = (val) => {
    if (typeof val !== "number") return val;
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
  };

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/lost_potential", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        missed_opportunities: parseFloat(missedOpportunities),
        time_delayed: parseFloat(timeDelayed),
        gains_from_action: parseFloat(gainsFromAction)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#ff4d4d" }}>Lost Potential</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Missed Opp.</label><input type="number" style={inputStyle} value={missedOpportunities} onChange={(e)=>setMissedOpportunities(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Delay (Days)</label><input type="number" style={inputStyle} value={timeDelayed} onChange={(e)=>setTimeDelayed(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Est. Gains</label><input type="number" style={inputStyle} value={gainsFromAction} onChange={(e)=>setGainsFromAction(e.target.value)} /></div>
      </div>
      <button style={{ backgroundColor: "#ff4d4d", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Calculate Lost Value</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #660000" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#ff4d4d" }}>{key.includes("value") || key.includes("cost") || key.includes("potential") ? formatCurrency(val) : val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
