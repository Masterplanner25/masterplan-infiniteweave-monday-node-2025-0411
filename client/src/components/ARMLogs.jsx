// src/components/ARMLogs.jsx
import React, { useEffect, useState } from "react";
import { getARMLogs } from "../api";

export default function ARMLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    // Avoid showing the "Loading..." flicker every 5 seconds for a smoother UI
    try {
      const res = await getARMLogs();
      setLogs(Array.isArray(res) ? res : res.logs ?? []);
    } catch (e) {
      setLogs([{ 
        timestamp: new Date().toISOString(), 
        level: "ERROR", 
        message: `System Error: ${String(e)}` 
      }]);
    }
  };

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
    
    const iv = setInterval(load, 5000); 
    return () => clearInterval(iv);
  }, []);

  // Helper to color code log levels
  const getLevelColor = (level) => {
    switch (level?.toUpperCase()) {
      case "ERROR": return "#ff6b6b";
      case "WARNING": return "#ffd93d";
      case "SUCCESS": return "#6bc11f";
      default: return "#4dabf7"; // INFO
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", fontFamily: "monospace" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h1 style={{ color: "#fff", margin: 0 }}>ARM — Logs</h1>
        {loading && <span style={{ color: "#555", fontSize: "12px" }}>Syncing...</span>}
      </div>

      <div style={{ 
        background: "#0d1117", 
        border: "1px solid #30363d", 
        borderRadius: "8px", 
        overflow: "hidden" 
      }}>
        {logs.length === 0 && !loading && (
          <div style={{ padding: "20px", color: "#555" }}>No logs recorded yet.</div>
        )}

        {logs.map((l, i) => (
          <div key={i} style={{ 
            padding: "10px 15px", 
            borderBottom: "1px solid #21262d",
            backgroundColor: i % 2 === 0 ? "transparent" : "#161b22" // Zebra striping
          }}>
            <div style={{ fontSize: "11px", marginBottom: "4px" }}>
              <span style={{ color: "#8b949e", marginRight: "10px" }}>{l.timestamp}</span>
              <span style={{ 
                color: getLevelColor(l.level), 
                fontWeight: "bold",
                fontSize: "10px",
                textTransform: "uppercase",
                border: `1px solid ${getLevelColor(l.level)}`,
                padding: "1px 4px",
                borderRadius: "3px"
              }}>
                {l.level ?? "INFO"}
              </span>
            </div>
            <div style={{ 
              whiteSpace: "pre-wrap", 
              color: "#c9d1d9", 
              fontSize: "13px",
              lineHeight: "1.4"
            }}>
              {l.message ?? JSON.stringify(l)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}