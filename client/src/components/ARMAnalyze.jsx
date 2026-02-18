// src/components/ARMAnalyze.jsx
import React, { useState } from "react";
import { runARMAnalysis } from "../api";

export default function ARMAnalyze() {
  const [filePath, setFilePath] = useState("tests/example.py");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Common styles to ensure visibility
  const inputStyle = {
    width: "60%",
    padding: "10px",
    backgroundColor: "#1a1a1a",
    color: "#fff",
    border: "1px solid #333",
    borderRadius: "6px",
    outline: "none"
  };

  const buttonStyle = {
    marginLeft: 8,
    padding: "10px 16px",
    backgroundColor: loading ? "#333" : "#007bff",
    color: "white",
    border: "none",
    borderRadius: "6px",
    cursor: loading ? "not-allowed" : "pointer",
    fontWeight: "bold"
  };

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runARMAnalysis(filePath);
      setResult(res.analysis ?? res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", fontFamily: "sans-serif" }}>
      <h1 style={{ color: "#fff", marginBottom: "20px" }}>ARM — Analyze</h1>

      <div style={{ marginBottom: 20 }}>
        <input
          type="text"
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          style={inputStyle}
          placeholder="File path (e.g. tests/example.py)"
        />
        <button onClick={submit} style={buttonStyle} disabled={loading}>
          {loading ? "Analyzing..." : "Run Analysis"}
        </button>
      </div>

      {error && (
        <div style={{ padding: "12px", background: "#441111", border: "1px solid #ff4444", borderRadius: "6px", color: "#ff8888", marginBottom: "12px" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ color: "#4dabf7", marginBottom: "10px" }}>Analysis Result</h3>
          <pre style={{ 
            whiteSpace: "pre-wrap", 
            background: "#0d1117", // GitHub Dark style background
            color: "#c9d1d9",       // Light gray text for readability
            padding: "16px", 
            borderRadius: "8px",
            border: "1px solid #30363d",
            fontSize: "14px",
            lineHeight: "1.6",
            fontFamily: "'Courier New', Courier, monospace",
            overflowX: "auto"
          }}>
            {result}
          </pre>
        </div>
      )}
    </div>
  );
}