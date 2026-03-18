import React, { useEffect, useState } from "react";

export default function HealthDashboard() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/dashboard/health");
        const json = await res.json();
        setLogs(json.logs || []);
      } catch (err) {
        setError("Failed to load health logs");
      } finally {
        setLoading(false);
      }
    };
    fetchLogs();
  }, []);

  if (loading) return <p>Loading health dashboard...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  const uptime =
    logs.filter((l) => l.status === "healthy").length / (logs.length || 1) * 100;

  return (
    <div style={{ padding: "1.5rem" }}>
      <h2 style={{ color: "#6cf" }}>🩺 A.I.N.D.Y. System Health</h2>
      <p>Uptime: {uptime.toFixed(1)}%</p>

      <table
        style={{
          width: "100%",
          marginTop: "1rem",
          borderCollapse: "collapse",
          fontSize: "0.9rem",
        }}
      >
        <thead>
          <tr style={{ background: "#111", color: "#6cf" }}>
            <th style={{ padding: "0.5rem", textAlign: "left" }}>Timestamp</th>
            <th>Status</th>
            <th>Avg Latency (ms)</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #333" }}>
              <td>{new Date(log.timestamp).toLocaleString()}</td>
              <td
                style={{
                  color:
                    log.status === "healthy"
                      ? "#4caf50"
                      : log.status === "degraded"
                      ? "#ffb300"
                      : "#f44336",
                }}
              >
                {log.status}
              </td>
              <td>{log.avg_latency_ms?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
