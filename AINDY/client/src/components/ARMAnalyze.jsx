// src/components/ARMAnalyze.jsx
import React, { useState } from "react";
import { runARMAnalysis } from "../api";

const SEVERITY_COLORS = {
  critical: "#ff4444",
  high: "#ff8c00",
  medium: "#ffd93d",
  low: "#4dabf7",
};

const CATEGORY_LABELS = {
  architecture: "Architecture",
  performance: "Performance",
  integrity: "Integrity",
  improvement: "Improvement",
};

function ScoreBadge({ label, score }) {
  const color = score >= 8 ? "#51cf66" : score >= 5 ? "#ffd93d" : "#ff6b6b";
  return (
    <div style={{ textAlign: "center", padding: "12px 16px", background: "#161b22", borderRadius: "8px", border: "1px solid #30363d", minWidth: 90 }}>
      <div style={{ fontSize: 28, fontWeight: "bold", color }}>{score}</div>
      <div style={{ fontSize: 11, color: "#8b949e", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function MetricBadge({ label, value }) {
  return (
    <div style={{ padding: "6px 12px", background: "#0d1117", border: "1px solid #21262d", borderRadius: "6px", fontSize: 12, color: "#8b949e" }}>
      <span style={{ color: "#c9d1d9", fontWeight: "bold" }}>{value}</span>{" "}
      {label}
    </div>
  );
}

export default function ARMAnalyze() {
  const [filePath, setFilePath] = useState("tests/example.py");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const inputStyle = {
    width: "60%",
    padding: "10px",
    backgroundColor: "#1a1a1a",
    color: "#fff",
    border: "1px solid #333",
    borderRadius: "6px",
    outline: "none",
  };

  const buttonStyle = {
    marginLeft: 8,
    padding: "10px 16px",
    backgroundColor: loading ? "#333" : "#007bff",
    color: "white",
    border: "none",
    borderRadius: "6px",
    cursor: loading ? "not-allowed" : "pointer",
    fontWeight: "bold",
  };

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runARMAnalysis(filePath);
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", fontFamily: "sans-serif", maxWidth: 900 }}>
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
        <div style={{ padding: "12px", background: "#441111", border: "1px solid #ff4444", borderRadius: "6px", color: "#ff8888", marginBottom: 12 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 20 }}>
          {/* Summary */}
          {result.summary && (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "16px", marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Summary</div>
              <p style={{ margin: 0, color: "#c9d1d9", lineHeight: 1.6 }}>{result.summary}</p>
            </div>
          )}

          {/* Scores */}
          {(result.architecture_score || result.performance_score || result.integrity_score) && (
            <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
              {result.architecture_score != null && <ScoreBadge label="Architecture" score={result.architecture_score} />}
              {result.performance_score != null && <ScoreBadge label="Performance" score={result.performance_score} />}
              {result.integrity_score != null && <ScoreBadge label="Integrity" score={result.integrity_score} />}
            </div>
          )}

          {/* Infinity Metrics */}
          {(result.execution_seconds != null || result.task_priority != null || result.execution_speed != null) && (
            <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
              {result.execution_seconds != null && <MetricBadge label="sec" value={result.execution_seconds} />}
              {result.task_priority != null && <MetricBadge label="task priority" value={result.task_priority} />}
              {result.execution_speed != null && <MetricBadge label="tok/s" value={result.execution_speed} />}
              {result.input_tokens != null && <MetricBadge label="in tok" value={result.input_tokens} />}
              {result.output_tokens != null && <MetricBadge label="out tok" value={result.output_tokens} />}
            </div>
          )}

          {/* Findings */}
          {result.findings && result.findings.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>Findings ({result.findings.length})</div>
              {result.findings.map((f, i) => (
                <div key={i} style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: "6px", padding: "12px 16px", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: "bold", color: SEVERITY_COLORS[f.severity] || "#4dabf7", border: `1px solid ${SEVERITY_COLORS[f.severity] || "#4dabf7"}`, padding: "1px 5px", borderRadius: 3, textTransform: "uppercase" }}>
                      {f.severity}
                    </span>
                    <span style={{ fontSize: 10, color: "#555", background: "#0d1117", padding: "1px 5px", borderRadius: 3, textTransform: "uppercase" }}>
                      {CATEGORY_LABELS[f.category] || f.category}
                    </span>
                    <span style={{ fontSize: 13, color: "#e6edf3", fontWeight: "bold" }}>{f.title}</span>
                  </div>
                  <p style={{ margin: "0 0 6px", color: "#8b949e", fontSize: 13, lineHeight: 1.5 }}>{f.description}</p>
                  {f.recommendation && (
                    <div style={{ fontSize: 12, color: "#51cf66" }}>
                      <strong>Recommendation:</strong> {f.recommendation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Overall recommendation */}
          {result.overall_recommendation && (
            <div style={{ background: "#0d1117", border: "1px solid #21262d", borderRadius: "8px", padding: "12px 16px" }}>
              <div style={{ fontSize: 11, color: "#51cf66", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>Overall Recommendation</div>
              <p style={{ margin: 0, color: "#c9d1d9", fontSize: 13 }}>{result.overall_recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
