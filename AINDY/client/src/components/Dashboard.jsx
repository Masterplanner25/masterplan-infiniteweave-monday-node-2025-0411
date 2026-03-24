import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getDashboardOverview } from "../api";
import FlowEngineConsole from "./FlowEngineConsole";
import GraphView from "./GraphView";

const C = {
  bg1: "#161b22",
  border0: "#21262d",
  text0: "#c9d1d9",
  text1: "#8b949e",
  accent: "#6cf",
};

function OverviewTab({ data }) {
  if (!data) return <p>Loading dashboard...</p>;

  return (
    <div>
      <h2 style={{ color: "#6cf" }}>System Overview</h2>
      <p>🧠 System Timestamp: {data.system_timestamp}</p>
      <p>👤 Total Authors: {data.author_count}</p>

      <h3 style={{ marginTop: "1rem", color: "#9f6" }}>Recent Authors</h3>
      <ul>
        {data.recent_authors.map((a) => (
          <li key={a.id}>
            {a.name} — {a.platform}
          </li>
        ))}
      </ul>

      <h3 style={{ marginTop: "1rem", color: "#f6f" }}>Recent Ripples</h3>
      <ul>
        {data.recent_ripples.map((r, i) => (
          <li key={i}>
            {r.summary} ({r.source_platform})
          </li>
        ))}
      </ul>
    </div>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "execution", label: "Execution" },
  { id: "graph", label: "Graph" },
];

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
          borderBottom: `1px solid ${C.border0}`,
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabClick(tab.id)}
            style={{
              padding: "8px 18px",
              background: "none",
              border: "none",
              borderBottom:
                activeTab === tab.id
                  ? `2px solid ${C.accent}`
                  : "2px solid transparent",
              color: activeTab === tab.id ? C.accent : C.text1,
              cursor: "pointer",
              fontSize: 13,
              fontWeight: activeTab === tab.id ? "bold" : "normal",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && <OverviewTab data={data} />}
      {activeTab === "execution" && <FlowEngineConsole />}
      {activeTab === "graph" && <GraphView />}
    </div>
  );
}
