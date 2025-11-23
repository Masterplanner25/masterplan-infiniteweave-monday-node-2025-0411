// src/components/ARMConfig.jsx
import React, { useEffect, useState } from "react";
import { getARMConfig, updateARMConfig } from "../api";

export default function ARMConfig() {
  const [config, setConfig] = useState({});
  const [param, setParam] = useState("");
  const [value, setValue] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await getARMConfig();
        setConfig(res.runtime_config ?? res);
      } catch (e) {
        setConfig({});
      }
    })();
  }, []);

  const save = async () => {
    try {
      await updateARMConfig(param, value);
      // refresh
      const res = await getARMConfig();
      setConfig(res.runtime_config ?? res);
      setParam("");
      setValue("");
      alert("Config updated");
    } catch (e) {
      alert("Update failed: " + e);
    }
  };

  return (
    <div>
      <h1>ARM — Config</h1>

      <div style={{ marginBottom: 12 }}>
        <h3>Current Runtime Config</h3>
        <pre style={{ background: "#f6f8fa", padding: 12 }}>{JSON.stringify(config, null, 2)}</pre>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input placeholder="parameter" value={param} onChange={(e) => setParam(e.target.value)} />
        <input placeholder="value" value={value} onChange={(e) => setValue(e.target.value)} />
        <button onClick={save}>Update</button>
      </div>
    </div>
  );
}
