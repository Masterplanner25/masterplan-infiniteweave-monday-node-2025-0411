import { useState } from "react";

export default function ImpactPanel() {
  const [reach, setReach] = useState(0);
  const [engagement, setEngagement] = useState(0);
  const [conversion, setConversion] = useState(0);
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
    fontSize: "14px",
    width: "100%",
    boxSizing: "border-box"
  };

  const labelStyle = {
    fontSize: "11px",
    color: "#888",
    display: "block",
    marginBottom: "4px"
  };

  const buttonStyle = {
    backgroundColor: "#e67e22", // Impact Orange
    color: "#fff",
    border: "none",
    padding: "12px",
    borderRadius: "6px",
    cursor: "pointer",
    fontWeight: "bold",
    width: "100%",
    marginTop: "10px",
    transition: "background 0.2s"
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch("http://localhost:8000/calculate_impact_score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reach: parseInt(reach),
          engagement: parseInt(engagement),
          conversion: parseInt(conversion)
        })
      });

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Impact Calculation Error:", err);
    }
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#e67e22" }}>Impact Score</h3>

      {/* 3-Column Grid for perfect alignment */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div>
          <label style={labelStyle}>Reach</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={reach} 
            onChange={(e)=>setReach(e.target.value)} 
          />
        </div>
        <div>
          <label style={labelStyle}>Engagement</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={engagement} 
            onChange={(e)=>setEngagement(e.target.value)} 
          />
        </div>
        <div>
          <label style={labelStyle}>Conversion</label>
          <input 
            type="number" 
            style={inputStyle} 
            value={conversion} 
            onChange={(e)=>setConversion(e.target.value)} 
          />
        </div>
      </div>

      <button style={buttonStyle} onClick={handleSubmit}>
        Calculate Impact
      </button>

      {result && (
        <pre style={{ 
          marginTop: "15px", 
          padding: "12px", 
          background: "#0a0a0a", 
          color: "#ffb366", 
          fontSize: "12px", 
          borderRadius: "4px",
          border: "1px solid #4d2600",
          overflowX: "auto"
        }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}