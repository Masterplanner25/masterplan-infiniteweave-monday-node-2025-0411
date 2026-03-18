import { useState } from "react";

export default function AttentionValuePanel() {
  const [contentOutput, setContentOutput] = useState(0);
  const [platformPresence, setPlatformPresence] = useState(0);
  const [time, setTime] = useState(0);
  const [result, setResult] = useState(null);

  const panelStyle = { backgroundColor: "#141414", padding: "15px", borderRadius: "8px", border: "1px solid #222", marginBottom: "15px" };
  const inputStyle = { backgroundColor: "#222", color: "#fff", border: "1px solid #444", padding: "10px", borderRadius: "4px", width: "100%", boxSizing: "border-box" };

  const handleSubmit = async () => {
    const response = await fetch("http://localhost:8000/attention_value", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content_output: parseFloat(contentOutput),
        platform_presence: parseFloat(platformPresence),
        time: parseFloat(time)
      })
    });
    setResult(await response.json());
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#e74c3c" }}>Attention Value</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
        <input style={inputStyle} type="number" placeholder="Output" value={contentOutput} onChange={(e)=>setContentOutput(e.target.value)} />
        <input style={inputStyle} type="number" placeholder="Presence" value={platformPresence} onChange={(e)=>setPlatformPresence(e.target.value)} />
        <input style={inputStyle} type="number" placeholder="Time" value={time} onChange={(e)=>setTime(e.target.value)} />
      </div>
      <button style={{ backgroundColor: "#e74c3c", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", width: "100%", fontWeight: "bold" }} onClick={handleSubmit}>Calculate Value</button>
      {result && <pre style={{ marginTop: "10px", padding: "10px", background: "#000", color: "#e74c3c", fontSize: "12px", borderRadius: "4px", border: "1px solid #333" }}>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}
