import { useState } from "react";

export default function IncomeEfficiencyPanel() {
  const [focusedEffort, setFocusedEffort] = useState(0);
  const [aiUtilization, setAiUtilization] = useState(0);
  const [time, setTime] = useState(0);
  const [capital, setCapital] = useState(0);
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
    padding: "10px", 
    borderRadius: "4px", 
    width: "100%", 
    boxSizing: "border-box" 
  };
  
  const labelStyle = { 
    fontSize: "11px", 
    color: "#888", 
    display: "block", 
    marginBottom: "4px",
    textTransform: "uppercase"
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch("http://localhost:8000/income_efficiency", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          focused_effort: parseFloat(focusedEffort),
          ai_utilization: parseFloat(aiUtilization),
          time: parseFloat(time),
          capital: parseFloat(capital)
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Income Efficiency Error:", err);
      alert("Calculation failed. Ensure the backend endpoint /income_efficiency exists.");
    }
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#2ecc71" }}>Income Efficiency</h3>
      
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "12px" }}>
        <div>
          <label style={labelStyle}>Focused Effort</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={focusedEffort} 
            onChange={(e)=>setFocusedEffort(e.target.value)} 
          />
        </div>
        <div>
          <label style={labelStyle}>AI Utilization</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={aiUtilization} 
            onChange={(e)=>setAiUtilization(e.target.value)} 
          />
        </div>
        <div>
          <label style={labelStyle}>Time Spent</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={time} 
            onChange={(e)=>setTime(e.target.value)} 
          />
        </div>
        <div>
          <label style={labelStyle}>Capital</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={capital} 
            onChange={(e)=>setCapital(e.target.value)} 
          />
        </div>
      </div>

      <button 
        style={{ 
          backgroundColor: "#2ecc71", 
          color: "#000", 
          border: "none", 
          padding: "12px", 
          borderRadius: "6px", 
          cursor: "pointer", 
          width: "100%", 
          fontWeight: "bold" 
        }} 
        onClick={handleSubmit}
      >
        Calculate Efficiency
      </button>

      {result && (
        <pre style={{ 
          marginTop: "15px", 
          padding: "12px", 
          background: "#000", 
          color: "#2ecc71", 
          fontSize: "12px", 
          borderRadius: "4px",
          border: "1px solid #145a32",
          whiteSpace: "pre-wrap"
        }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}