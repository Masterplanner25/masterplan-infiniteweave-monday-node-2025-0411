import { useState, useEffect, useCallback } from "react";
import { getARMConfigSuggestions, updateARMConfig } from "../api";

// ── Helpers ──────────────────────────────────────────────────────────────────

const PRIORITY_STYLES = {
  critical: { bg: "#450a0a", border: "#ef4444", badge: "#ef4444", text: "#fca5a5" },
  warning:  { bg: "#422006", border: "#f97316", badge: "#f97316", text: "#fdba74" },
  info:     { bg: "#0f172a", border: "#334155", badge: "#64748b", text: "#94a3b8" },
};

const RISK_STYLES = {
  low:    { color: "#22c55e" },
  medium: { color: "#eab308" },
  high:   { color: "#ef4444" },
  none:   { color: "#64748b" },
};

function PriorityBadge({ priority }) {
  const s = PRIORITY_STYLES[priority] || PRIORITY_STYLES.info;
  return (
    <span style={{
      padding: "2px 10px",
      borderRadius: 12,
      background: s.bg,
      border: `1px solid ${s.border}`,
      color: s.text,
      fontSize: 11,
      fontWeight: 700,
      textTransform: "uppercase",
    }}>
      {priority}
    </span>
  );
}

function RiskBadge({ risk }) {
  const s = RISK_STYLES[risk] || RISK_STYLES.none;
  return (
    <span style={{ fontSize: 11, color: s.color, fontWeight: 600 }}>
      Risk: {risk}
    </span>
  );
}

// ── Suggestion card ───────────────────────────────────────────────────────────

function SuggestionCard({ suggestion, onApply, applying }) {
  const hasChange = suggestion.config_change &&
    Object.keys(suggestion.config_change).length > 0;

  const s = PRIORITY_STYLES[suggestion.priority] || PRIORITY_STYLES.info;

  return (
    <div style={{
      background: s.bg,
      border: `1px solid ${s.border}`,
      borderRadius: 8,
      padding: "16px 20px",
      display: "flex",
      flexDirection: "column",
      gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <PriorityBadge priority={suggestion.priority} />
        <span style={{ fontSize: 12, color: "#64748b" }}>
          metric: <strong style={{ color: "#94a3b8" }}>{suggestion.metric}</strong>
        </span>
        <RiskBadge risk={suggestion.risk} />
      </div>

      <div>
        <div style={{ fontSize: 13, color: "#e2e8f0", marginBottom: 4 }}>
          {suggestion.issue}
        </div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          {suggestion.suggestion}
        </div>
      </div>

      {hasChange && (
        <pre style={{
          margin: 0,
          padding: "8px 12px",
          background: "#0f172a",
          borderRadius: 4,
          fontSize: 11,
          color: "#7dd3fc",
          overflowX: "auto",
        }}>
          {JSON.stringify(suggestion.config_change, null, 2)}
        </pre>
      )}

      <div style={{ fontSize: 11, color: "#64748b" }}>
        Expected: {suggestion.expected_impact}
      </div>

      {hasChange && (
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => onApply(suggestion.config_change)}
            disabled={applying}
            style={{
              padding: "6px 16px",
              borderRadius: 4,
              border: "none",
              background: applying ? "#334155" : "#3b82f6",
              color: "#fff",
              cursor: applying ? "default" : "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {applying ? "Applying…" : "Apply This Change"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ARMConfigSuggest() {
  const [window, setWindow] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [applyingKey, setApplyingKey] = useState(null); // tracks which apply is in flight
  const [successMsg, setSuccessMsg] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getARMConfigSuggestions(window)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [window]);

  useEffect(() => { load(); }, [load]);

  async function applyChange(configChange, key) {
    setApplyingKey(key);
    try {
      await updateARMConfig(configChange);
      setSuccessMsg("Config updated successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
      load(); // refresh suggestions
    } catch (e) {
      setError(`Apply failed: ${e.message}`);
    } finally {
      setApplyingKey(null);
    }
  }

  async function applyAllLowRisk() {
    if (!data?.auto_apply_safe?.length) return;
    const combined = data.combined_suggested_config;
    const safeKeys = Object.keys(
      data.auto_apply_safe.reduce((acc, s) => ({ ...acc, ...s.config_change }), {})
    );
    const safeOnly = Object.fromEntries(
      safeKeys.map((k) => [k, combined[k]])
    );
    await applyChange(safeOnly, "all-low-risk");
  }

  const suggestions = data?.suggestions ?? [];
  const byPriority = ["critical", "warning", "info"];

  return (
    <div style={{ padding: 24, color: "#e2e8f0", fontFamily: "monospace" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 20, color: "#f8fafc" }}>
          Config Suggestions
        </h2>
        <div style={{ display: "flex", gap: 8 }}>
          {[7, 30, 90].map((d) => (
            <button key={d} onClick={() => setWindow(d)} style={{
              padding: "4px 12px", borderRadius: 4,
              border: "1px solid #334155",
              background: window === d ? "#3b82f6" : "#1e293b",
              color: window === d ? "#fff" : "#94a3b8",
              cursor: "pointer", fontSize: 12,
            }}>
              {d}d
            </button>
          ))}
        </div>
        <button onClick={load} disabled={loading} style={{
          marginLeft: "auto", padding: "6px 14px", borderRadius: 4,
          border: "1px solid #334155", background: "#1e293b",
          color: "#94a3b8", cursor: loading ? "default" : "pointer", fontSize: 12,
        }}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {successMsg && (
        <div style={{
          padding: "10px 16px", background: "#052e16", border: "1px solid #22c55e",
          borderRadius: 6, color: "#86efac", fontSize: 13, marginBottom: 16,
        }}>
          {successMsg}
        </div>
      )}
      {error && (
        <div style={{
          padding: "10px 16px", background: "#450a0a", border: "1px solid #ef4444",
          borderRadius: 6, color: "#fca5a5", fontSize: 13, marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* Metrics snapshot */}
      {data?.metrics_snapshot && (
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 16,
          padding: "12px 16px", background: "#0f172a",
          borderRadius: 6, marginBottom: 20, fontSize: 12,
        }}>
          <span style={{ color: "#94a3b8" }}>
            Decision: <strong style={{ color: "#e2e8f0" }}>
              {data.metrics_snapshot.decision_efficiency}%
            </strong>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Speed avg: <strong style={{ color: "#e2e8f0" }}>
              {data.metrics_snapshot.execution_speed_avg} tok/s
            </strong>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Productivity: <strong style={{ color: "#e2e8f0" }}>
              {data.metrics_snapshot.ai_productivity_ratio}
            </strong>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Waste: <strong style={{ color: "#e2e8f0" }}>
              {data.metrics_snapshot.waste_percentage}%
            </strong>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Trend: <strong style={{ color: "#e2e8f0" }}>
              {data.metrics_snapshot.learning_trend}
            </strong>
          </span>
          <span style={{ color: "#64748b" }}>
            {data.metrics_snapshot.total_sessions} sessions
          </span>
        </div>
      )}

      {/* Apply all low-risk button */}
      {data?.auto_apply_safe?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <button
            onClick={applyAllLowRisk}
            disabled={applyingKey === "all-low-risk"}
            style={{
              padding: "8px 20px", borderRadius: 4, border: "none",
              background: "#15803d", color: "#fff",
              cursor: applyingKey === "all-low-risk" ? "default" : "pointer",
              fontSize: 13, fontWeight: 600,
            }}
          >
            {applyingKey === "all-low-risk"
              ? "Applying…"
              : `Apply All Low-Risk (${data.auto_apply_safe.length})`}
          </button>
          <span style={{ marginLeft: 12, fontSize: 12, color: "#64748b" }}>
            {data.apply_instruction}
          </span>
        </div>
      )}

      {/* Suggestion cards grouped by priority */}
      {byPriority.map((priority) => {
        const group = suggestions.filter((s) => s.priority === priority);
        if (!group.length) return null;
        return (
          <div key={priority} style={{ marginBottom: 20 }}>
            <div style={{
              fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
              color: "#64748b", marginBottom: 10,
            }}>
              {priority} ({group.length})
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {group.map((s, i) => (
                <SuggestionCard
                  key={i}
                  suggestion={s}
                  onApply={(change) => applyChange(change, `${priority}-${i}`)}
                  applying={applyingKey === `${priority}-${i}`}
                />
              ))}
            </div>
          </div>
        );
      })}

      {!loading && suggestions.length === 0 && (
        <div style={{ color: "#64748b", fontSize: 13 }}>No suggestions loaded.</div>
      )}
    </div>
  );
}
