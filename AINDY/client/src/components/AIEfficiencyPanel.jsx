import { useState } from "react";

export default function AIEfficiencyPanel() {
  const [aiContributions, setAiContributions] = useState(0);
  const [humanContributions, setHumanContributions] = useState(0);
  const [totalTasks, setTotalTasks] = useState(0);
  const [result, setResult] = useState(null);

  // --- Internal Styles ---
  const panelStyle = {
    backgroundColor: "#141414",
    padding: "15px",
    borderRadius: "8px",
    border: "1px solid #222",
    marginBottom: "15px"
  };

  const inputStyle = {
    backgroundColor: "#222",
    color: "#fff",
    border: "1px solid #444",
    padding: "8px",
    borderRadius: "4px",
    fontSize: "14px",
    width: "100%", // This ensures they stack nicely or fill their container
    marginBottom: "10px"
  };

  const buttonStyle = {
    backgroundColor: "#17a2b8", // Distinct teal color for efficiency
    color: "#fff",
    border: "none",
    padding: "10px 15px",
    borderRadius: "6px",
    cursor: "pointer",
    fontWeight: "bold",
    width: "100%"
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch("http://localhost:8000/calculate_ai_efficiency", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_contributions: parseInt(aiContributions),
          human_contributions: parseInt(humanContributions),
          total_tasks: parseInt(totalTasks)
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Efficiency Calculation Error:", err);
    }
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#17a2b8" }}>AI Efficiency</h3>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div>
          <label style={{ fontSize: "11px", color: "#888" }}>AI Contr.</label>
          <input 
            type="number" 
            style={inputStyle} 
            placeholder="AI" 
            value={aiContributions} 
            onChange={(e)=>setAiContributions(e.target.value)} 
          />
        </div>
        <div>
          <label style={{ fontSize: "11px", color: "#888" }}>Human Contr.</label>
          <input 
            type="number" 
            style={inputStyle} 
            placeholder="Human" 
            value={humanContributions} 
            onChange={(e)=>setHumanContributions(e.target.value)} 
          />
        </div>
        <div>
          <label style={{ fontSize: "11px", color: "#888" }}>Total Tasks</label>
          <input 
            type="number" 
            style={inputStyle} 
            placeholder="Total" 
            value={totalTasks} 
            onChange={(e)=>setTotalTasks(e.target.value)} 
          />
        </div>
      </div>

      <button style={buttonStyle} onClick={handleSubmit}>
        Calculate AI Efficiency
      </button>

      {result && (
        <pre style={{ 
          marginTop: "12px", 
          padding: "10px", 
          background: "#0a0a0a", 
          color: "#17a2b8", 
          fontSize: "12px", 
          borderRadius: "4px",
          border: "1px solid #222",
          overflowX: "auto"
        }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}