// src/components/ARMGenerate.jsx
import React, { useState } from "react";
import { runARMGenerate } from "../../api/arm.js";
import { safeMap } from "../../utils/safe";

const LANGUAGES = ["python", "javascript", "typescript", "jsx", "tsx", "json", "yaml", "markdown"];

export default function ARMGenerate() {
  const [prompt, setPrompt] = useState("Refactor the following into async functions with proper error handling.");
  const [originalCode, setOriginalCode] = useState("");
  const [language, setLanguage] = useState("python");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const inputBaseStyle = {
    backgroundColor: "#1a1a1a",
    color: "#fff",
    border: "1px solid #333",
    borderRadius: "6px",
    padding: "10px",
    outline: "none",
    fontFamily: "inherit",
    width: "100%",
    boxSizing: "border-box"
  };

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runARMGenerate(prompt, { original_code: originalCode, language });
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", maxWidth: 900, fontFamily: "sans-serif" }}>
      <h1 style={{ color: "#fff", marginBottom: "20px" }}>ARM — Generate</h1>

      {/* Language selector */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: 6, color: "#999", fontSize: "0.85rem" }}>Language</label>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          style={{ ...inputBaseStyle, width: "auto", cursor: "pointer" }}>
          
          {safeMap(LANGUAGES, (l) =>
          <option key={l} value={l}>{l}</option>)
          }
        </select>
      </div>

      {/* Prompt */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: 6, color: "#999", fontSize: "0.85rem" }}>
          Prompt / Instructions
        </label>
        <textarea
          rows={4}
          style={{ ...inputBaseStyle, lineHeight: "1.5" }}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the code you want to generate or refactor..." />
        
      </div>

      {/* Optional: existing code to refactor */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: 6, color: "#999", fontSize: "0.85rem" }}>
          Existing Code to Refactor <span style={{ color: "#555" }}>(optional)</span>
        </label>
        <textarea
          rows={6}
          style={{ ...inputBaseStyle, lineHeight: "1.5", fontFamily: "'Fira Code', 'Courier New', monospace", fontSize: 13 }}
          value={originalCode}
          onChange={(e) => setOriginalCode(e.target.value)}
          placeholder="Paste existing code here if refactoring..." />
        
      </div>

      <button
        onClick={submit}
        disabled={loading}
        style={{
          padding: "10px 20px",
          backgroundColor: loading ? "#333" : "#007bff",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: loading ? "not-allowed" : "pointer",
          fontWeight: "bold",
          opacity: loading ? 0.7 : 1
        }}>
        
        {loading ? "Generating..." : "Generate Code"}
      </button>

      {error &&
      <div style={{ marginTop: 20, color: "#ff6b6b", background: "rgba(255,0,0,0.1)", padding: "12px", borderRadius: "6px", border: "1px solid #ff4444" }}>
          {error}
        </div>
      }

      {result &&
      <div style={{ marginTop: 24 }}>
          {/* Metrics row */}
          {(result.execution_seconds != null || result.task_priority != null) &&
        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              {result.execution_seconds != null &&
          <span style={{ fontSize: 12, color: "#8b949e", background: "#0d1117", border: "1px solid #21262d", padding: "4px 10px", borderRadius: 6 }}>
                  <strong style={{ color: "#c9d1d9" }}>{result.execution_seconds}s</strong> execution
                </span>
          }
              {result.task_priority != null &&
          <span style={{ fontSize: 12, color: "#8b949e", background: "#0d1117", border: "1px solid #21262d", padding: "4px 10px", borderRadius: 6 }}>
                  <strong style={{ color: "#c9d1d9" }}>{result.task_priority}</strong> task priority
                </span>
          }
              {result.confidence != null &&
          <span style={{ fontSize: 12, color: "#8b949e", background: "#0d1117", border: "1px solid #21262d", padding: "4px 10px", borderRadius: 6 }}>
                  <strong style={{ color: "#51cf66" }}>{result.confidence}/10</strong> confidence
                </span>
          }
            </div>
        }

          {/* Explanation */}
          {result.explanation &&
        <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "12px 16px", marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Explanation</div>
              <p style={{ margin: 0, color: "#c9d1d9", fontSize: 13, lineHeight: 1.6 }}>{result.explanation}</p>
            </div>
        }

          {/* Generated Code */}
          {result.generated_code &&
        <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h3 style={{ margin: 0, color: "#4dabf7" }}>Generated Code</h3>
                <button
              onClick={() => navigator.clipboard.writeText(result.generated_code)}
              style={{ background: "transparent", border: "1px solid #444", color: "#999", cursor: "pointer", fontSize: 12, padding: "4px 8px", borderRadius: 4 }}>
              
                  Copy
                </button>
              </div>
              <pre style={{
            background: "#0d1117",
            color: "#d1d5db",
            padding: "20px",
            borderRadius: "8px",
            border: "1px solid #30363d",
            whiteSpace: "pre-wrap",
            fontFamily: "'Fira Code', 'Courier New', monospace",
            fontSize: 13,
            lineHeight: 1.6,
            overflowX: "auto"
          }}>
                {result.generated_code}
              </pre>
            </div>
        }

          {/* Quality Notes */}
          {result.quality_notes &&
        <div style={{ background: "#0d1117", border: "1px solid #21262d", borderRadius: "6px", padding: "10px 14px", marginTop: 10 }}>
              <div style={{ fontSize: 11, color: "#ffd93d", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>Quality Notes</div>
              <p style={{ margin: 0, color: "#8b949e", fontSize: 12 }}>{result.quality_notes}</p>
            </div>
        }
        </div>
      }
    </div>);

}
