// src/components/ARMGenerate.jsx
import React, { useState } from "react";
import { runARMGenerate } from "../api";

export default function ARMGenerate() {
  const [filePath, setFilePath] = useState("tests/example.py");
  const [instructions, setInstructions] = useState("Refactor into async functions");
  const [loading, setLoading] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);

  // Reusable style for a dark, visible input system
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
    setCode("");
    try {
      const res = await runARMGenerate(filePath, instructions);
      setCode(res.generated_code ?? JSON.stringify(res, null, 2));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", maxWidth: "900px" }}>
      <h1 style={{ color: "#fff", marginBottom: "20px" }}>ARM — Generate</h1>

      {/* FILE PATH INPUT */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: "8px", color: "#999", fontSize: "0.85rem" }}>
          Target File Path
        </label>
        <input
          style={{ ...inputBaseStyle, width: "60%" }}
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          placeholder="e.g. src/app.py"
        />
      </div>

      {/* INSTRUCTIONS TEXTAREA */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: "8px", color: "#999", fontSize: "0.85rem" }}>
          Generation Instructions
        </label>
        <textarea
          rows={5}
          style={{ ...inputBaseStyle, width: "100%", lineHeight: "1.5" }}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Describe the changes or code you want to generate..."
        />
      </div>

      <div>
        <button 
          onClick={submit} 
          disabled={loading} 
          style={{ 
            padding: "10px 20px", 
            backgroundColor: "#007bff", 
            color: "white", 
            border: "none", 
            borderRadius: "6px", 
            cursor: loading ? "not-allowed" : "pointer",
            fontWeight: "bold",
            opacity: loading ? 0.7 : 1
          }}
        >
          {loading ? "Generating..." : "Generate Code"}
        </button>
      </div>

      {/* ERROR DISPLAY */}
      {error && (
        <pre style={{ 
          marginTop: 20, 
          color: "#ff6b6b", 
          background: "rgba(255, 0, 0, 0.1)", 
          padding: "12px", 
          borderRadius: "6px", 
          border: "1px solid #ff4444" 
        }}>
          {error}
        </pre>
      )}

      {/* GENERATED CODE OUTPUT */}
      {code && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <h3 style={{ margin: 0, color: "#4dabf7" }}>Generated Code</h3>
            <button 
              onClick={() => navigator.clipboard.writeText(code)}
              style={{ background: "transparent", border: "1px solid #444", color: "#999", cursor: "pointer", fontSize: "12px", padding: "4px 8px", borderRadius: "4px" }}
            >
              Copy Code
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
            fontSize: "14px",
            lineHeight: "1.6",
            overflowX: "auto"
          }}>
            {code}
          </pre>
        </div>
      )}
    </div>
  );
}