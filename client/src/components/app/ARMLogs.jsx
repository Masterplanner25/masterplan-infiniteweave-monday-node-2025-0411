// src/components/ARMLogs.jsx
import React, { useEffect, useState } from "react";
import { getARMLogs } from "../../api";import { safeMap } from "../../utils/safe";

function MetricPill({ label, value, color }) {
  return (
    <span style={{ fontSize: 11, color: color || "#8b949e", background: "#0d1117", border: "1px solid #21262d", padding: "2px 8px", borderRadius: 4, marginRight: 6 }}>
      <strong style={{ color: color || "#c9d1d9" }}>{value}</strong> {label}
    </span>);

}

export default function ARMLogs() {
  const [data, setData] = useState({ analyses: [], generations: [], summary: null });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const res = await getARMLogs();
      if (res && typeof res === "object" && "analyses" in res) {
        setData(res);
      }
    } catch (e) {
      console.error("[ARMLogs]", e);
    }
  };

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, []);

  const { analyses, generations, summary } = data;
  const hasData = analyses.length > 0 || generations.length > 0;

  return (
    <div style={{ padding: "20px", color: "#eee", fontFamily: "monospace", maxWidth: 900 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ color: "#fff", margin: 0 }}>ARM — Logs</h1>
        {loading && <span style={{ color: "#555", fontSize: 12 }}>Syncing...</span>}
      </div>

      {/* Summary Row */}
      {summary &&
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
          <MetricPill label="analyses" value={summary.total_analyses} />
          <MetricPill label="generations" value={summary.total_generations} />
          <MetricPill label="total tokens" value={summary.total_tokens_used?.toLocaleString()} color="#4dabf7" />
        </div>
      }

      {!hasData && !loading &&
      <div style={{ padding: "20px", color: "#555", background: "#0d1117", border: "1px solid #21262d", borderRadius: 8 }}>
          No ARM sessions recorded yet.
        </div>
      }

      {/* Analysis History */}
      {analyses.length > 0 &&
      <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
            Analysis Sessions ({analyses.length})
          </div>
          <div style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
            {safeMap(analyses, (a, i) =>
          <div key={i} style={{ padding: "12px 16px", borderBottom: i < analyses.length - 1 ? "1px solid #21262d" : "none", backgroundColor: i % 2 === 0 ? "transparent" : "#161b22" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                  <span style={{
                fontSize: 10, fontWeight: "bold",
                color: a.status === "success" ? "#51cf66" : "#ff6b6b",
                border: `1px solid ${a.status === "success" ? "#51cf66" : "#ff6b6b"}`,
                padding: "1px 5px", borderRadius: 3, textTransform: "uppercase"
              }}>
                    {a.status ?? "unknown"}
                  </span>
                  <span style={{ color: "#c9d1d9", fontSize: 13, fontWeight: "bold" }}>{a.file || "—"}</span>
                  <span style={{ color: "#555", fontSize: 11 }}>{a.created_at?.replace("T", " ").split(".")[0] ?? ""}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", marginBottom: a.summary ? 6 : 0 }}>
                  {a.execution_seconds != null && <MetricPill label="s" value={a.execution_seconds} />}
                  {a.task_priority != null && <MetricPill label="TP" value={a.task_priority} />}
                  {a.execution_speed != null && <MetricPill label="tok/s" value={a.execution_speed} color="#4dabf7" />}
                  {a.input_tokens != null && <MetricPill label="in" value={a.input_tokens} />}
                  {a.output_tokens != null && <MetricPill label="out" value={a.output_tokens} />}
                </div>
                {a.summary &&
            <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.5, marginTop: 4 }}>{a.summary}</div>
            }
              </div>)
          }
          </div>
        </div>
      }

      {/* Generation History */}
      {generations.length > 0 &&
      <div>
          <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
            Generation Sessions ({generations.length})
          </div>
          <div style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
            {safeMap(generations, (g, i) =>
          <div key={i} style={{ padding: "12px 16px", borderBottom: i < generations.length - 1 ? "1px solid #21262d" : "none", backgroundColor: i % 2 === 0 ? "transparent" : "#161b22" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 10, color: "#4dabf7", border: "1px solid #4dabf7", padding: "1px 5px", borderRadius: 3, textTransform: "uppercase" }}>
                    {g.generation_type ?? "generate"}
                  </span>
                  <span style={{ color: "#c9d1d9", fontSize: 13 }}>{g.language ?? "—"}</span>
                  <span style={{ color: "#555", fontSize: 11 }}>{g.created_at?.replace("T", " ").split(".")[0] ?? ""}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap" }}>
                  {g.execution_seconds != null && <MetricPill label="s" value={g.execution_seconds} />}
                  {g.input_tokens != null && <MetricPill label="in tok" value={g.input_tokens} />}
                  {g.output_tokens != null && <MetricPill label="out tok" value={g.output_tokens} />}
                </div>
              </div>)
          }
          </div>
        </div>
      }
    </div>);

}