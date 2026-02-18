import { useState } from "react";

export default function BusinessGrowthPanel() {
  const [revenue, setRevenue] = useState(0);
  const [expenses, setExpenses] = useState(0);
  const [scalingFriction, setScalingFriction] = useState(0);
  const [result, setResult] = useState(null);

  const formatCurrency = (val) => {
    if (typeof val !== "number") return val;
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
  };

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/business_growth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        revenue: parseFloat(revenue),
        expenses: parseFloat(expenses),
        scaling_friction: parseFloat(scalingFriction)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#2ecc71" }}>Business Growth</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Revenue</label><input type="number" style={inputStyle} value={revenue} onChange={(e)=>setRevenue(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Expenses</label><input type="number" style={inputStyle} value={expenses} onChange={(e)=>setExpenses(e.target.value)} /></div>
        <div><label style={{ fontSize: "11px", color: "#888" }}>Friction</label><input type="number" style={inputStyle} value={scalingFriction} onChange={(e)=>setScalingFriction(e.target.value)} /></div>
      </div>
      <button style={{ backgroundColor: "#2ecc71", color: "#000", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Analyze Growth</button>
      
      {result && (
        <div style={{ marginTop: "15px", padding: "10px", background: "#000", borderRadius: "4px", border: "1px solid #145a32" }}>
          {Object.entries(result).map(([key, val]) => (
            <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#888" }}>{key.replace(/_/g, " ")}:</span>
              <span style={{ color: "#2ecc71" }}>{key.includes("profit") || key.includes("revenue") ? formatCurrency(val) : val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}