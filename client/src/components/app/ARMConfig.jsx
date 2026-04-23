// src/components/ARMConfig.jsx
import React, { useEffect, useState } from "react";
import { getARMConfig, updateARMConfig } from "../../api/arm.js";
import { Toast } from "../shared/Toast";
import { useToast } from "../../utils/useToast";

export default function ARMConfig() {
  const [config, setConfig] = useState({});
  const [param, setParam] = useState("");
  const [value, setValue] = useState("");
  const [validationError, setValidationError] = useState("");
  const { toast, showToast, clearToast } = useToast();

  // Reusable style for the configuration inputs
  const inputStyle = {
    padding: "10px",
    backgroundColor: "#1a1a1a",
    color: "#fff",
    border: "1px solid #333",
    borderRadius: "6px",
    outline: "none",
    flex: 1
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await getARMConfig();
        setConfig(res.config ?? res.runtime_config ?? res);
      } catch (e) {
        setConfig({});
      }
    })();
  }, []);

  const save = async () => {
    if (!param) {
      setValidationError("Please enter a parameter name.");
      return;
    }
    try {
      // Parse numeric values; leave strings as strings
      const parsedValue = value === "" ? value : isNaN(Number(value)) ? value : Number(value);
      await updateARMConfig({ [param]: parsedValue });
      const res = await getARMConfig();
      setConfig(res.config ?? res.runtime_config ?? res);
      setParam("");
      setValue("");
      setValidationError("");
      showToast("Config updated successfully.", "success");
    } catch (e) {
      showToast(e?.message || String(e) || "Update failed.");
    }
  };

  return (
    <div style={{ padding: "20px", color: "#eee", fontFamily: "sans-serif" }}>
      <h1 style={{ color: "#fff", marginBottom: "20px" }}>ARM — Config</h1>

      <div style={{ marginBottom: 24 }}>
        <h3 style={{ color: "#999", fontSize: "0.9rem", marginBottom: "10px", textTransform: "uppercase" }}>
          Current Runtime Config
        </h3>
        <pre style={{ 
          background: "#0d1117", 
          color: "#79c0ff", // Light blue text for JSON keys/values
          padding: "16px", 
          borderRadius: "8px", 
          border: "1px solid #30363d",
          fontSize: "14px",
          fontFamily: "'Courier New', Courier, monospace",
          overflowX: "auto"
        }}>
          {JSON.stringify(config, null, 2)}
        </pre>
      </div>

      <div style={{ 
        background: "#141414", 
        padding: "20px", 
        borderRadius: "8px", 
        border: "1px solid #222" 
      }}>
        <h3 style={{ color: "#fff", fontSize: "1.1rem", marginBottom: "15px" }}>Update Parameter</h3>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <input 
            style={inputStyle}
            placeholder="parameter (e.g. max_tokens)" 
            value={param} 
            onChange={(e) => {
              setParam(e.target.value);
              setValidationError("");
            }} 
          />
          <input 
            style={inputStyle}
            placeholder="value" 
            value={value} 
            onChange={(e) => setValue(e.target.value)} 
          />
          <button 
            onClick={save}
            style={{
              padding: "10px 20px",
              backgroundColor: "#238636", // GitHub-style green for "Success/Update"
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "bold",
              transition: "background 0.2s"
            }}
            onMouseOver={(e) => e.target.style.backgroundColor = "#2ea043"}
            onMouseOut={(e) => e.target.style.backgroundColor = "#238636"}
          >
            Update
          </button>
        </div>
        {validationError && <div style={{ color: "#f87171", fontSize: "12px", marginTop: "10px" }}>{validationError}</div>}
      </div>
      <Toast toast={toast} onDismiss={clearToast} />
    </div>
  );
}
