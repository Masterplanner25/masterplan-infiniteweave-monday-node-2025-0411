import { useState } from "react";

export default function ExecutionSpeedPanel() {
  const [aiAutomations, setAiAutomations] = useState(0);
  const [systemizedWorkflows, setSystemizedWorkflows] = useState(0);
  const [decisionLag, setDecisionLag] = useState(0);
  const [result, setResult] = useState(null);

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/execution_speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ai_automations: parseFloat(aiAutomations),
        systemized_workflows: parseFloat(systemizedWorkflows),
        decision_lag: parseFloat(decisionLag)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#3498db" }}>Execution Speed</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <input style={inputStyle} type="number" placeholder="AI Autom." value={aiAutomations} onChange={(e)=>setAiAutomations(e.target.value)} />
        <input style={inputStyle} type="number" placeholder="Workflows" value={systemizedWorkflows} onChange={(e)=>setSystemizedWorkflows(e.target.value)} />
        <input style={inputStyle} type="number" placeholder="Dec. Lag" value={decisionLag} onChange={(e)=>setDecisionLag(e.target.value)} />
      </div>
      <button style={{ backgroundColor: "#3498db", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Calculate Speed</button>
      {result && <pre style={{ marginTop: "10px", padding: "10px", background: "#000", color: "#3498db", fontSize: "12px", borderRadius: "4px", border: "1px solid #333" }}>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}