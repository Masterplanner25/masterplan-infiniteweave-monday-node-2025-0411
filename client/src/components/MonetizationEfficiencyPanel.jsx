import { useState } from "react";

export default function MonetizationEfficiencyPanel() {
  const [totalRevenue, setTotalRevenue] = useState(0);
  const [audienceSize, setAudienceSize] = useState(0);
  const [result, setResult] = useState(null);

  const formatCurrency = (val) => {
    if (typeof val !== "number") return val;
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
  };

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/monetization_efficiency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        total_revenue: parseFloat(totalRevenue),
        audience_size: parseFloat(audienceSize)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#f1c40f" }}>Monetization Efficiency</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div>
          <label style={{ fontSize: "11px", color: "#888" }}>Total Revenue</label>
          <input type="number" style={inputStyle} value={totalRevenue} onChange={(e)=>setTotalRevenue(e.target.value)} />
        </div>
        <div>
          <label style={{ fontSize: "11px", color: "#888" }}>Audience Size</label>
          <input type="number" style={inputStyle} value={audienceSize} onChange={(e)=>setAudienceSize(e.target.value)} />
        </div>
      </div>
      <button style={{ backgroundColor: "#f1c40f", color: "#000", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Calculate</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #333" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#f1c40f" }}>{key.includes("revenue") || key.includes("value") ? formatCurrency(val) : val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}