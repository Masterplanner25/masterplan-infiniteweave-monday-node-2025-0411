// src/components/ARMLogs.jsx
import React, { useEffect, useState } from "react";
import { getARMLogs } from "../api";

export default function ARMLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await getARMLogs();
      // If backend returns raw array
      setLogs(Array.isArray(res) ? res : res.logs ?? []);
    } catch (e) {
      setLogs([{ timestamp: new Date().toISOString(), level: "ERROR", message: String(e) }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const iv = setInterval(load, 5000); // auto-refresh every 5s
    return () => clearInterval(iv);
  }, []);

  return (
    <div>
      <h1>ARM — Logs</h1>
      {loading && <div>Loading...</div>}
      <div style={{ marginTop: 12 }}>
        {logs.length === 0 && <div>No logs yet</div>}
        {logs.map((l, i) => (
          <div key={i} style={{ padding: 8, borderBottom: "1px solid #eee" }}>
            <div style={{ fontSize: 12, color: "#555" }}>
              [{l.timestamp}] {l.level ?? "INFO"}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{l.message ?? JSON.stringify(l)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
