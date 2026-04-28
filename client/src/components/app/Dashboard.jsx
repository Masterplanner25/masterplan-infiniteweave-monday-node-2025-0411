import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getDashboardOverview } from "../../api/legacy.js";
import { getMyScore, recalculateScore, getScoreHistory } from "../../api/product.js";
import { useAuth } from "../../context/AuthContext";
import { useSystem } from "../../context/SystemContext";
import GraphView from "./GraphView";import { safeMap } from "../../utils/safe";
import { Toast } from "../shared/Toast";
import { useToast } from "../../utils/useToast";

const PLATFORM_BASE = import.meta.env.VITE_PLATFORM_BASE_URL ?? "/platform";

const C = {
  bg1: "#161b22",
  border0: "#21262d",
  text0: "#c9d1d9",
  text1: "#8b949e",
  accent: "#6cf"
};

const KPI_META = {
  execution_speed: { label: "Execution Speed", weight: "25%" },
  decision_efficiency: { label: "Decision Quality", weight: "25%" },
  ai_productivity_boost: { label: "AI Leverage", weight: "20%" },
  focus_quality: { label: "Focus Quality", weight: "15%" },
  masterplan_progress: { label: "Plan Progress", weight: "15%" }
};

function scoreColor(score) {
  if (score >= 70) return "#4caf50";
  if (score >= 40) return "#ffc107";
  return "#f44336";
}

function ScoreRing({ score }) {
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const filled = score / 100 * circumference;
  const color = scoreColor(score);
  return (
    <svg width={110} height={110} style={{ display: "block", margin: "0 auto" }}>
      <circle cx={55} cy={55} r={radius} fill="none" stroke="#21262d" strokeWidth={10} />
      <circle
        cx={55} cy={55} r={radius}
        fill="none"
        stroke={color}
        strokeWidth={10}
        strokeDasharray={`${filled} ${circumference}`}
        strokeLinecap="round"
        transform="rotate(-90 55 55)"
        style={{ transition: "stroke-dasharray 0.6s ease" }} />

      <text x={55} y={60} textAnchor="middle" fill={color} fontSize={22} fontWeight="bold">
        {score.toFixed(1)}
      </text>
    </svg>);

}

function InfinityScorePanel() {
  const { system } = useSystem();
  const [score, setScore] = useState(system.metrics);
  const [history, setHistory] = useState([]);
  const [recalculating, setRecalculating] = useState(false);
  const { toast, showToast, clearToast } = useToast();

  const loadScore = () => {
    getMyScore().then(setScore).catch(() => setScore(null));
    getScoreHistory(14).then((d) => setHistory(d?.history || [])).catch(() => setHistory([]));
  };

  useEffect(() => {loadScore();}, []);
  useEffect(() => {
    if (system.metrics) {
      setScore(system.metrics);
    }
  }, [system.metrics]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      const result = await recalculateScore();
      setScore(result);
      getScoreHistory(14).then((d) => setHistory(d?.history || [])).catch(() => {});
    } catch (e) {
      console.error("Recalculate failed", e);
      showToast(e?.message || "Recalculate failed. Please try again.");
    } finally {
      setRecalculating(false);
    }
  };

  const masterScore = score?.master_score ?? 0;
  const kpis = score?.kpis ?? {};
  const meta = score?.metadata ?? {};

  return (
    <div style={{
      background: "#0d1117",
      border: "1px solid #21262d",
      borderRadius: 10,
      padding: "20px 24px",
      marginBottom: 24
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ margin: 0, color: "#6cf", fontSize: 16 }}>Infinity Score</h2>
        <button
          onClick={handleRecalculate}
          disabled={recalculating}
          style={{
            background: "#21262d",
            border: "1px solid #30363d",
            color: "#c9d1d9",
            borderRadius: 6,
            padding: "4px 12px",
            cursor: recalculating ? "not-allowed" : "pointer",
            fontSize: 12
          }}>

          {recalculating ? "Calculating..." : "Recalculate"}
        </button>
      </div>

      {/* Master Score Ring */}
      <div style={{ textAlign: "center", marginBottom: 20 }}>
        <ScoreRing score={masterScore} />
        <div style={{ marginTop: 6, fontSize: 12, color: "#8b949e" }}>
          {meta.confidence &&
          <span style={{
            background: meta.confidence === "high" ? "#1a3a1a" : meta.confidence === "medium" ? "#3a2a00" : "#2a1a1a",
            color: meta.confidence === "high" ? "#4caf50" : meta.confidence === "medium" ? "#ffc107" : "#f44336",
            borderRadius: 4, padding: "2px 8px", marginRight: 8, fontSize: 11
          }}>
              {meta.confidence} confidence
            </span>
          }
          {meta.calculated_at && `Updated ${new Date(meta.calculated_at).toLocaleTimeString()}`}
        </div>
        {score?.message &&
        <p style={{ color: "#8b949e", fontSize: 12, marginTop: 8 }}>{score.message}</p>
        }
      </div>

      {/* KPI Grid */}
      {Object.keys(kpis).length > 0 &&
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
        gap: 10,
        marginBottom: 20
      }}>
          {safeMap(Object.entries(KPI_META), ([key, { label, weight }]) => {
          const val = kpis[key] ?? 0;
          const color = scoreColor(val);
          return (
            <div key={key} style={{
              background: "#161b22",
              border: "1px solid #21262d",
              borderRadius: 8,
              padding: "10px 12px"
            }}>
                <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 4 }}>{label}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <div style={{
                  flex: 1, height: 4, background: "#21262d", borderRadius: 2, overflow: "hidden"
                }}>
                    <div style={{
                    width: `${val}%`, height: "100%", background: color,
                    borderRadius: 2, transition: "width 0.4s ease"
                  }} />
                  </div>
                  <span style={{ fontSize: 12, color, fontWeight: "bold", minWidth: 36 }}>
                    {val.toFixed(1)}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: "#6e7681" }}>{weight} of total</div>
              </div>);

        })}
        </div>
      }

      {/* Score History Sparkline */}
      {history.length > 1 &&
      <div>
          <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 6 }}>Score History</div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 40 }}>
            {safeMap(history.slice().reverse(), (h, i) => {
            const barH = Math.max(4, h.master_score / 100 * 40);
            const delta = h.score_delta;
            const barColor = delta === null ? "#6cf" : delta >= 0 ? "#4caf50" : "#f44336";
            return (
              <div key={i} title={`${h.master_score.toFixed(1)} (${delta !== null ? (delta >= 0 ? "+" : "") + delta.toFixed(1) : "—"})`}
              style={{
                flex: 1, height: barH, background: barColor,
                borderRadius: 2, cursor: "default", transition: "height 0.3s ease"
              }} />);


          })}
          </div>
        </div>
      }
      <Toast toast={toast} onDismiss={clearToast} />
    </div>);

}

function IdentityBootSummary() {
  const { system } = useSystem();
  const summary = system?.system_state || {};

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
      gap: 12,
      marginBottom: 24
    }}>
      {safeMap([
      ["Booted Memory", summary.memory_count ?? 0, "#00ffaa"],
      ["Active Runs", summary.active_runs ?? 0, "#60a5fa"],
      ["Active Flows", summary.active_flows ?? 0, "#f59e0b"],
      ["Current Score", summary.score ?? "—", "#f472b6"]],
      ([label, value, color]) =>
      <div key={label} style={{
        background: "#0d1117",
        border: "1px solid #21262d",
        borderRadius: 10,
        padding: "14px 16px"
      }}>
          <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 6 }}>{label}</div>
          <div style={{ fontSize: 26, fontWeight: 800, color }}>
            {typeof value === "number" ? value : value}
          </div>
        </div>)
      }
    </div>);

}

function OverviewTab({ data }) {
  if (!data) return <p>Loading dashboard...</p>;

  return (
    <div>
      <h2 style={{ color: "#6cf" }}>System Overview</h2>
      <p>🧠 System Timestamp: {data.system_timestamp}</p>
      <p>👤 Total Authors: {data.author_count}</p>

      <h3 style={{ marginTop: "1rem", color: "#9f6" }}>Recent Authors</h3>
      <ul>
        {safeMap(data.recent_authors, (a) =>
        <li key={a.id}>
            {a.name} — {a.platform}
          </li>)
        }
      </ul>

      <h3 style={{ marginTop: "1rem", color: "#f6f" }}>Recent Ripples</h3>
      <ul>
        {safeMap(data.recent_ripples, (r, i) =>
        <li key={i}>
            {r.summary} ({r.source_platform})
          </li>)
        }
      </ul>
    </div>);

}

function ExecutionTab() {
  const { isAdmin } = useAuth();

  if (!isAdmin) {
    return (
      <div style={{ color: "#8b949e" }}>
        Platform execution tools are available to admin users only.
      </div>
    );
  }

  return (
    <div
      style={{
        background: "#0d1117",
        border: "1px solid #21262d",
        borderRadius: 10,
        padding: "20px 24px",
      }}
    >
      <h2 style={{ color: "#6cf", marginTop: 0 }}>Execution Console</h2>
      <p style={{ color: "#8b949e", marginBottom: 16 }}>
        The execution console now lives in the dedicated platform admin app.
      </p>
      <a
        href={`${PLATFORM_BASE}/flows`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          background: "#6cf",
          color: "#000",
          borderRadius: 6,
          padding: "10px 14px",
          fontWeight: "bold",
          textDecoration: "none",
        }}
      >
        Open Platform Console
      </a>
    </div>
  );
}

const TABS = [
{ id: "overview", label: "Overview" },
{ id: "execution", label: "Execution" },
{ id: "graph", label: "Graph" }];


export default function Dashboard() {
  const [data, setData] = useState(null);
  const [localTab, setLocalTab] = useState("overview");
  const location = useLocation();
  const navigate = useNavigate();
  const isGraphRoute = location.pathname === "/dashboard/graph";
  const activeTab = isGraphRoute ? "graph" : localTab;

  useEffect(() => {
    const fetchData = async () => {
      const json = await getDashboardOverview();
      setData(json.overview);
    };
    fetchData();
  }, []);

  const handleTabClick = (tabId) => {
    if (tabId === "graph") {
      if (!isGraphRoute) navigate("/dashboard/graph");
      return;
    }
    if (isGraphRoute) {
      navigate("/dashboard");
    }
    setLocalTab(tabId);
  };

  return (
    <div style={{ color: C.text0, fontFamily: "sans-serif" }}>
      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: 2,
          marginBottom: 20,
          borderBottom: `1px solid ${C.border0}`
        }}>

        {safeMap(TABS, (tab) =>
        <button
          key={tab.id}
          onClick={() => handleTabClick(tab.id)}
          style={{
            padding: "8px 18px",
            background: "none",
            border: "none",
            borderBottom:
            activeTab === tab.id ?
            `2px solid ${C.accent}` :
            "2px solid transparent",
            color: activeTab === tab.id ? C.accent : C.text1,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: activeTab === tab.id ? "bold" : "normal"
          }}>

            {tab.label}
          </button>)
        }
      </div>

      {activeTab === "overview" &&
      <>
          <IdentityBootSummary />
          <InfinityScorePanel />
          <OverviewTab data={data} />
        </>
      }
      {activeTab === "execution" && <ExecutionTab />}
      {activeTab === "graph" && <GraphView />}
    </div>);

}
