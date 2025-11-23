// src/components/ARMGenerate.jsx
import React, { useState } from "react";
import { runARMGenerate } from "../api";

export default function ARMGenerate() {
  const [filePath, setFilePath] = useState("tests/example.py");
  const [instructions, setInstructions] = useState("Refactor into async functions");
  const [loading, setLoading] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);

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
    <div>
      <h1>ARM — Generate</h1>

      <div style={{ marginBottom: 12 }}>
        <input
          style={{ width: "60%", padding: 8 }}
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <textarea
          rows={6}
          style={{ width: "80%", padding: 8 }}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </div>

      <div>
        <button onClick={submit} disabled={loading} style={{ padding: "8px 12px" }}>
          {loading ? "Generating..." : "Generate Code"}
        </button>
      </div>

      {error && <pre style={{ color: "red" }}>{error}</pre>}

      {code && (
        <div style={{ marginTop: 12 }}>
          <h3>Generated Code</h3>
          <pre style={{ background: "#f6f8fa", padding: 12, whiteSpace: "pre-wrap" }}>{code}</pre>
        </div>
      )}
    </div>
  );
}
