// src/components/ARMAnalyze.jsx
import React, { useState } from "react";
import { runARMAnalysis } from "../api";

export default function ARMAnalyze() {
  const [filePath, setFilePath] = useState("tests/example.py");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

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
    <div>
      <h1>ARM — Analyze</h1>

      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          style={{ width: "60%", padding: 8 }}
        />
        <button onClick={submit} style={{ marginLeft: 8, padding: "8px 12px" }} disabled={loading}>
          {loading ? "Analyzing..." : "Run Analysis"}
        </button>
      </div>

      {error && <pre style={{ color: "red" }}>{error}</pre>}

      {result && (
        <div style={{ marginTop: 12 }}>
          <h3>Analysis Result</h3>
          <pre style={{ whiteSpace: "pre-wrap", background: "#f6f8fa", padding: 12 }}>{result}</pre>
        </div>
      )}
    </div>
  );
}
