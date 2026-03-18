import { useState } from "react";

export default function DecisionEfficiencyPanel() {
  const [automatedDecisions, setAutomatedDecisions] = useState(0);
  const [manualDecisions, setManualDecisions] = useState(0);
  const [processingTime, setProcessingTime] = useState(0);
  const [result, setResult] = useState(null);

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/decision_efficiency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        automated_decisions: parseFloat(automatedDecisions),
        manual_decisions: parseFloat(manualDecisions),
        processing_time: parseFloat(processingTime)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#00d4ff" }}>Decision Efficiency</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Automated</label><input type="number" style={inputStyle} value={automatedDecisions} onChange={(e)=>setAutomatedDecisions(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Manual</label><input type="number" style={inputStyle} value={manualDecisions} onChange={(e)=>setManualDecisions(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Time (ms)</label><input type="number" style={inputStyle} value={processingTime} onChange={(e)=>setProcessingTime(e.target.value)} /></div>
      </div>
      <button style={{ backgroundColor: "#00d4ff", color: "#000", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Analyze Decisions</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #004d66" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#00d4ff" }}>{val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}