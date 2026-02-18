import { useState } from "react";

export default function AIProductivityBoostPanel() {
  const [tasksWithAI, setTasksWithAI] = useState(0);
  const [tasksWithoutAI, setTasksWithoutAI] = useState(0);
  const [timeSaved, setTimeSaved] = useState(0);
  const [result, setResult] = useState(null);

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/ai_productivity_boost", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tasks_with_ai: parseFloat(tasksWithAI),
        tasks_without_ai: parseFloat(tasksWithoutAI),
        time_saved: parseFloat(timeSaved)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#00ffaa" }}>AI Productivity Boost</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div><label style={{ fontSize: "11px", color: "#888" }}>With AI</label><input type="number" style={inputStyle} value={tasksWithAI} onChange={(e)=>setTasksWithAI(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Without AI</label><input type="number" style={inputStyle} value={tasksWithoutAI} onChange={(e)=>setTasksWithoutAI(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Time Saved</label><input type="number" style={inputStyle} value={timeSaved} onChange={(e)=>setTimeSaved(e.target.value)} /></div>
      </div>
      <button style={{ backgroundColor: "#00ffaa", color: "#000", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Analyze Boost</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #006644" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#00ffaa" }}>{val}{key.includes("percent") || key.includes("increase") ? "%" : ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
