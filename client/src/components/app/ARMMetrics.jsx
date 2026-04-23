import { useState, useEffect } from "react";
import { getARMMetrics } from "../../api/arm.js";

// ── Helpers ──────────────────────────────────────────────────────────────────
import { safeMap } from "../../utils/safe";
function efficiencyColor(score) {
  if (score >= 80) return "#22c55e"; // green
  if (score >= 60) return "#eab308"; // yellow
  return "#ef4444"; // red
}

function wasteColor(pct) {
  if (pct < 5) return "#22c55e";
  if (pct < 15) return "#eab308";
  return "#ef4444";
}

function trendColor(trend) {
  if (trend === "improving") return "#22c55e";
  if (trend === "declining") return "#ef4444";
  return "#94a3b8"; // stable / insufficient data
}

function trendArrow(trend) {
  if (trend === "improving") return "↑";
  if (trend === "declining") return "↓";
  return "→";
}

// ── Card shell ────────────────────────────────────────────────────────────────

function MetricCard({ title, children }) {
  return (
    <div style={{
      background: "#1e293b",
      border: "1px solid #334155",
      borderRadius: 8,
      padding: "16px 20px",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }}>
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#64748b" }}>
        {title}
      </div>
      {children}
    </div>);

}

// ── Main component ────────────────────────────────────────────────────────────

export default function ARMMetrics() {
  const [window, setWindow] = useState(30);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getARMMetrics(window).
    then(setMetrics).
    catch((e) => setError(e.message)).
    finally(() => setLoading(false));
  }, [window]);

  return (
    <div style={{ padding: 24, color: "#e2e8f0", fontFamily: "monospace" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 20, color: "#f8fafc" }}>
          Thinking KPI System
        </h2>
        <div style={{ display: "flex", gap: 8 }}>
          {safeMap([7, 30, 90], (d) =>
          <button
            key={d}
            onClick={() => setWindow(d)}
            style={{
              padding: "4px 12px",
              borderRadius: 4,
              border: "1px solid #334155",
              background: window === d ? "#3b82f6" : "#1e293b",
              color: window === d ? "#fff" : "#94a3b8",
              cursor: "pointer",
              fontSize: 12
            }}>
            
              {d}d
            </button>)
          }
        </div>
        {metrics &&
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>
            {metrics.total_sessions} sessions · {metrics.window_days}d window
          </span>
        }
      </div>

      {loading && <div style={{ color: "#64748b" }}>Loading metrics…</div>}
      {error && <div style={{ color: "#ef4444" }}>Error: {error}</div>}

      {metrics &&
      <>
          <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 16,
          marginBottom: 20
        }}>

            {/* 1. Decision Efficiency */}
            <MetricCard title="Decision Efficiency">
              <div style={{
              fontSize: 40,
              fontWeight: 700,
              color: efficiencyColor(metrics.decision_efficiency?.score ?? 0)
            }}>
                {metrics.decision_efficiency?.score ?? 0}%
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                {metrics.decision_efficiency?.successful ?? 0} successful&nbsp;/&nbsp;
                {metrics.decision_efficiency?.total ?? 0} total sessions
              </div>
            </MetricCard>

            {/* 2. Execution Speed */}
            <MetricCard title="Execution Speed">
              <div style={{ fontSize: 28, fontWeight: 700, color: "#38bdf8" }}>
                {metrics.execution_speed?.current ?? 0}
                <span style={{ fontSize: 14, marginLeft: 4, color: "#64748b" }}>
                  {metrics.execution_speed?.unit}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                avg {metrics.execution_speed?.average ?? 0} · peak {metrics.execution_speed?.peak ?? 0}
              </div>
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {(metrics.execution_speed?.total_tokens ?? 0).toLocaleString()} total tokens processed
              </div>
            </MetricCard>

            {/* 3. AI Productivity Boost */}
            <MetricCard title="AI Productivity Boost">
              <div style={{ fontSize: 36, fontWeight: 700, color: "#a78bfa" }}>
                {metrics.ai_productivity_boost?.ratio ?? 0}
                <span style={{ fontSize: 13, marginLeft: 6, color: "#64748b" }}>ratio</span>
              </div>
              <span style={{
              display: "inline-block",
              padding: "2px 10px",
              borderRadius: 12,
              background: "#1e3a5f",
              color: "#93c5fd",
              fontSize: 11,
              width: "fit-content"
            }}>
                {metrics.ai_productivity_boost?.rating ?? "—"}
              </span>
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {(metrics.ai_productivity_boost?.input_tokens ?? 0).toLocaleString()} in →{" "}
                {(metrics.ai_productivity_boost?.output_tokens ?? 0).toLocaleString()} out
              </div>
            </MetricCard>

            {/* 4. Lost Potential */}
            <MetricCard title="Lost Potential">
              <div style={{
              fontSize: 36,
              fontWeight: 700,
              color: wasteColor(metrics.lost_potential?.waste_percentage ?? 0)
            }}>
                {metrics.lost_potential?.waste_percentage ?? 0}%
                <span style={{ fontSize: 13, marginLeft: 6, color: "#64748b" }}>wasted</span>
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                {(metrics.lost_potential?.wasted_tokens ?? 0).toLocaleString()} tokens ·{" "}
                {metrics.lost_potential?.wasted_seconds ?? 0}s
              </div>
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {metrics.lost_potential?.failed_sessions ?? 0} failed sessions
              </div>
            </MetricCard>

            {/* 5. Learning Efficiency */}
            <MetricCard title="Learning Efficiency">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{
                fontSize: 24,
                color: trendColor(metrics.learning_efficiency?.trend)
              }}>
                  {trendArrow(metrics.learning_efficiency?.trend)}
                </span>
                <span style={{
                padding: "4px 12px",
                borderRadius: 12,
                background: "#1e293b",
                border: `1px solid ${trendColor(metrics.learning_efficiency?.trend)}`,
                color: trendColor(metrics.learning_efficiency?.trend),
                fontSize: 13,
                fontWeight: 600
              }}>
                  {metrics.learning_efficiency?.trend ?? "—"}
                </span>
              </div>
              {metrics.learning_efficiency?.delta_percentage != null &&
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
                  {metrics.learning_efficiency.delta_percentage > 0 ? "+" : ""}
                  {metrics.learning_efficiency.delta_percentage}% speed change
                </div>
            }
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {metrics.learning_efficiency?.sessions_needed ?
              `${metrics.learning_efficiency.sessions_needed} more sessions needed` :
              `${metrics.decision_efficiency?.total ?? 0} sessions analyzed`}
              </div>
            </MetricCard>
          </div>

          {/* Summary bar */}
          <div style={{
          padding: "12px 16px",
          background: "#0f172a",
          borderRadius: 6,
          fontSize: 13,
          color: "#94a3b8"
        }}>
            {metrics.summary}
          </div>
        </>
      }
    </div>);

}
