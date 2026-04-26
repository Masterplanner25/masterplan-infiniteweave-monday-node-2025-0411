// src/components/AgentRegistry.jsx
import React, { useState, useEffect, useCallback } from "react";
import {
  getAgents,
  recallFromAgent,
  getFederatedMemory,
} from "../../api/agent.js";
import { useAuth } from "../../context/AuthContext";
import { AdminAccessRequired } from "../shared/AdminApiErrorBoundary";

// ── Constants ───────────────────────────────────────────────────────────────
import { safeMap } from "../../utils/safe";
const AGENT_META = {
  arm: { icon: "🧠", color: "#a78bfa", label: "ARM" },
  genesis: { icon: "🌐", color: "#60a5fa", label: "Genesis" },
  nodus: { icon: "⚡", color: "#ffd93d", label: "Nodus" },
  leadgen: { icon: "🎯", color: "#34d399", label: "LeadGen" },
  sylva: { icon: "🔮", color: "#94a3b8", label: "SYLVA" }
};

function agentMeta(namespace) {
  const key = (namespace || "").toLowerCase().replace(/[^a-z]/g, "");
  return AGENT_META[key] || { icon: "🤖", color: "#71717a", label: namespace || "Unknown" };
}

// ── Sub-components ──────────────────────────────────────────────────────────

function StatPill({ label, value, color }) {
  return (
    <div
      style={{
        background: "#09090b",
        borderRadius: 6,
        padding: "6px 12px",
        textAlign: "center",
        minWidth: 70
      }}>

      <div style={{ color: color || "#e4e4e7", fontWeight: 700, fontSize: 18 }}>{value ?? 0}</div>
      <div style={{ color: "#52525b", fontSize: 10, marginTop: 1 }}>{label}</div>
    </div>);

}

function AgentRecallPanel({ agent, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const meta = agentMeta(agent.memory_namespace || agent.name);

  async function handleRecall() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const data = await recallFromAgent(agent.memory_namespace || agent.name, query.trim(), 5);
      setResults(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const nodes = results?.memories || results?.results || [];

  return (
    <div
      style={{
        background: "#18181b",
        border: `1px solid ${meta.color}44`,
        borderRadius: 10,
        padding: 20,
        marginTop: 8
      }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ color: meta.color, fontSize: 13, fontWeight: 600 }}>
          Recall from {agent.name}
        </span>
        <button
          onClick={onClose}
          style={{ background: "transparent", border: "none", color: "#52525b", fontSize: 16, cursor: "pointer" }}>

          ✕
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRecall()}
          placeholder="Search this agent's memory…"
          style={{
            flex: 1,
            background: "#09090b",
            border: "1px solid #27272a",
            borderRadius: 6,
            color: "#e4e4e7",
            fontSize: 13,
            padding: "8px 12px",
            outline: "none"
          }} />

        <button
          onClick={handleRecall}
          disabled={loading || !query.trim()}
          style={{
            background: meta.color,
            border: "none",
            borderRadius: 6,
            color: "#09090b",
            fontWeight: 700,
            fontSize: 13,
            padding: "8px 16px",
            cursor: loading || !query.trim() ? "not-allowed" : "pointer",
            opacity: loading || !query.trim() ? 0.6 : 1
          }}>

          {loading ? "…" : "Recall"}
        </button>
      </div>

      {error &&
      <div style={{ color: "#fca5a5", fontSize: 12, padding: "6px 0" }}>{error}</div>
      }

      {nodes.length > 0 &&
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {safeMap(nodes, (node, i) =>
        <div
          key={node.id || i}
          style={{
            background: "#09090b",
            borderRadius: 8,
            padding: "10px 14px",
            borderLeft: `3px solid ${meta.color}`
          }}>

              <div style={{ color: "#e4e4e7", fontSize: 13, lineHeight: 1.5, marginBottom: 4 }}>
                {node.content || node.text || JSON.stringify(node)}
              </div>
              {node.resonance_score != null &&
          <div style={{ color: "#52525b", fontSize: 11 }}>
                  resonance {(node.resonance_score * 100).toFixed(0)}%
                </div>
          }
            </div>)
        }
        </div>
      }

      {results && nodes.length === 0 &&
      <div style={{ color: "#52525b", fontSize: 12, textAlign: "center", padding: "10px 0" }}>
          No memories found for that query.
        </div>
      }
    </div>);

}

function AgentCard({ agent, isSelected, onSelect }) {
  const meta = agentMeta(agent.memory_namespace || agent.name);
  const stats = agent.memory_stats || {};

  return (
    <div
      style={{
        background: "#18181b",
        border: `1px solid ${isSelected ? meta.color : "#27272a"}`,
        borderRadius: 10,
        padding: 20,
        cursor: "pointer",
        transition: "border-color 0.2s"
      }}
      onClick={onSelect}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 28 }}>{meta.icon}</span>
          <div>
            <div style={{ color: meta.color, fontWeight: 700, fontSize: 15 }}>{agent.name}</div>
            {agent.memory_namespace &&
            <div style={{ color: "#52525b", fontSize: 11 }}>ns: {agent.memory_namespace}</div>
            }
          </div>
        </div>
        <span
          style={{
            fontSize: 10,
            padding: "2px 8px",
            borderRadius: 99,
            fontWeight: 600,
            background: agent.is_active ? "#00ffaa22" : "#27272a",
            color: agent.is_active ? "#00ffaa" : "#52525b",
            border: `1px solid ${agent.is_active ? "#00ffaa44" : "#3f3f46"}`
          }}>

          {agent.is_active ? "Active" : "Inactive"}
        </span>
      </div>

      {/* Description */}
      {agent.description &&
      <div style={{ color: "#71717a", fontSize: 12, lineHeight: 1.5, marginBottom: 14 }}>
          {agent.description}
        </div>
      }

      {/* Stats */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <StatPill label="Total" value={stats.total_nodes} color={meta.color} />
        <StatPill label="Shared" value={stats.shared_nodes} color="#00ffaa" />
        <StatPill label="Private" value={stats.private_nodes} color="#71717a" />
      </div>

      {/* Recall button */}
      <div style={{ marginTop: 14 }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          style={{
            background: "transparent",
            border: `1px solid ${meta.color}`,
            borderRadius: 6,
            color: meta.color,
            fontSize: 12,
            padding: "5px 14px",
            cursor: "pointer"
          }}>

          {isSelected ? "▲ Close Recall" : "▼ Recall Memory"}
        </button>
      </div>
    </div>);

}

function FederatedSearchPanel({ agents }) {
  const [query, setQuery] = useState("");
  const [selectedNs, setSelectedNs] = useState([]);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const namespaces = safeMap(agents, (a) => a.memory_namespace || a.name).filter(Boolean);

  function toggleNs(ns) {
    setSelectedNs((prev) =>
    prev.includes(ns) ? prev.filter((x) => x !== ns) : [...prev, ns]
    );
  }

  async function handleFedSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const ns = selectedNs.length > 0 ? selectedNs : null;
      const data = await getFederatedMemory(query.trim(), ns, 10);
      setResults(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const nodes = results?.merged_results || results?.results || results?.memories || [];

  return (
    <div
      style={{
        background: "#18181b",
        border: "1px solid #27272a",
        borderRadius: 10,
        padding: 20,
        marginBottom: 24
      }}>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 18 }}>🌐</span>
        <span style={{ color: "#e4e4e7", fontWeight: 700, fontSize: 15 }}>Federated Recall</span>
        <span style={{ color: "#52525b", fontSize: 12, marginLeft: 4 }}>
          — search across all agents at once
        </span>
      </div>

      {/* Namespace filter chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        {safeMap(namespaces, (ns) => {
          const meta = agentMeta(ns);
          const active = selectedNs.includes(ns);
          return (
            <button
              key={ns}
              onClick={() => toggleNs(ns)}
              style={{
                background: active ? `${meta.color}22` : "transparent",
                border: `1px solid ${active ? meta.color : "#3f3f46"}`,
                borderRadius: 6,
                color: active ? meta.color : "#71717a",
                fontSize: 12,
                padding: "3px 10px",
                cursor: "pointer"
              }}>

              {meta.icon} {ns}
            </button>);

        })}
        {selectedNs.length > 0 &&
        <button
          onClick={() => setSelectedNs([])}
          style={{
            background: "transparent",
            border: "1px solid #3f3f46",
            borderRadius: 6,
            color: "#52525b",
            fontSize: 11,
            padding: "3px 10px",
            cursor: "pointer"
          }}>

            Clear filters
          </button>
        }
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleFedSearch()}
          placeholder={
          selectedNs.length > 0 ?
          `Search ${selectedNs.join(", ")}…` :
          "Search all agents…"
          }
          style={{
            flex: 1,
            background: "#09090b",
            border: "1px solid #27272a",
            borderRadius: 6,
            color: "#e4e4e7",
            fontSize: 13,
            padding: "8px 12px",
            outline: "none"
          }} />

        <button
          onClick={handleFedSearch}
          disabled={loading || !query.trim()}
          style={{
            background: "#60a5fa",
            border: "none",
            borderRadius: 6,
            color: "#09090b",
            fontWeight: 700,
            fontSize: 13,
            padding: "8px 16px",
            cursor: loading || !query.trim() ? "not-allowed" : "pointer",
            opacity: loading || !query.trim() ? 0.6 : 1
          }}>

          {loading ? "…" : "Search"}
        </button>
      </div>

      {error &&
      <div style={{ color: "#fca5a5", fontSize: 12, marginBottom: 8 }}>{error}</div>
      }

      {nodes.length > 0 &&
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {safeMap(nodes, (node, i) => {
          const srcMeta = agentMeta(node.source_agent || "");
          return (
            <div
              key={node.id || i}
              style={{
                background: "#09090b",
                borderRadius: 8,
                padding: "10px 14px",
                borderLeft: `3px solid ${srcMeta.color}`,
                display: "flex",
                gap: 10
              }}>

                <span style={{ fontSize: 16, marginTop: 1 }}>{srcMeta.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                    {node.source_agent &&
                  <span
                    style={{
                      fontSize: 10,
                      color: srcMeta.color,
                      background: `${srcMeta.color}22`,
                      borderRadius: 4,
                      padding: "1px 6px"
                    }}>

                        {node.source_agent}
                      </span>
                  }
                    {node.node_type &&
                  <span style={{ color: "#3f3f46", fontSize: 11 }}>{node.node_type}</span>
                  }
                    {node.resonance_score != null &&
                  <span style={{ color: "#52525b", fontSize: 11, marginLeft: "auto" }}>
                        {(node.resonance_score * 100).toFixed(0)}%
                      </span>
                  }
                  </div>
                  <div style={{ color: "#e4e4e7", fontSize: 13, lineHeight: 1.5 }}>
                    {node.content || node.text || JSON.stringify(node)}
                  </div>
                </div>
              </div>);

        })}
        </div>
      }

      {results && nodes.length === 0 &&
      <div style={{ color: "#52525b", fontSize: 12, textAlign: "center", padding: "10px 0" }}>
          No results across any agent.
        </div>
      }
    </div>);

}

// ── Main Component ──────────────────────────────────────────────────────────

export default function AgentRegistry() {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <AdminAccessRequired />;
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAgents();
      setAgents(data.agents || data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const containerStyle = {
    minHeight: "100vh",
    background: "#09090b",
    color: "#e4e4e7",
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
    padding: "28px 32px",
    maxWidth: 860,
    margin: "0 auto"
  };

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: "center", padding: 80, color: "#52525b" }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
          <div>Loading agent registry…</div>
        </div>
      </div>);

  }

  if (error) {
    return (
      <div style={containerStyle}>
        <div
          style={{
            background: "#7f1d1d",
            borderRadius: 10,
            padding: "20px 24px",
            color: "#fca5a5",
            display: "flex",
            alignItems: "center",
            gap: 12
          }}>

          <span style={{ fontSize: 20 }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Failed to load agents</div>
            <div style={{ fontSize: 13 }}>{error}</div>
          </div>
          <button
            onClick={loadAgents}
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "1px solid #fca5a5",
              borderRadius: 6,
              color: "#fca5a5",
              fontSize: 12,
              padding: "6px 14px",
              cursor: "pointer"
            }}>

            Retry
          </button>
        </div>
      </div>);

  }

  const activeAgents = agents.filter((a) => a.is_active);
  const inactiveAgents = agents.filter((a) => !a.is_active);

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ fontSize: 28 }}>🤖</span>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#e4e4e7" }}>Agent Federation</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ color: "#52525b", fontSize: 13 }}>
            All registered agents and their shared memory pools
          </span>
          <span
            style={{
              background: "#00ffaa22",
              border: "1px solid #00ffaa44",
              borderRadius: 6,
              color: "#00ffaa",
              fontSize: 12,
              padding: "2px 10px"
            }}>

            {activeAgents.length} active
          </span>
          {inactiveAgents.length > 0 &&
          <span
            style={{
              background: "#27272a",
              border: "1px solid #3f3f46",
              borderRadius: 6,
              color: "#52525b",
              fontSize: 12,
              padding: "2px 10px"
            }}>

              {inactiveAgents.length} inactive
            </span>
          }
        </div>
      </div>

      {/* Federated Search */}
      {agents.length > 0 && <FederatedSearchPanel agents={agents} />}

      {/* Empty state */}
      {agents.length === 0 &&
      <div
        style={{
          textAlign: "center",
          padding: "60px 0",
          color: "#52525b"
        }}>

          <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: "#71717a" }}>
            No agents registered
          </div>
          <div style={{ fontSize: 13 }}>
            Agents register themselves when first used. Try running ARM or Genesis.
          </div>
        </div>
      }

      {/* Active agents */}
      {activeAgents.length > 0 &&
      <div style={{ marginBottom: 24 }}>
          <div style={{ color: "#71717a", fontSize: 12, fontWeight: 600, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
            Active
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {safeMap(activeAgents, (agent) => {
            const ns = agent.memory_namespace || agent.name;
            const isSelected = selectedAgent === ns;
            return (
              <div key={agent.id || ns}>
                  <AgentCard
                  agent={agent}
                  isSelected={isSelected}
                  onSelect={() => setSelectedAgent(isSelected ? null : ns)} />

                  {isSelected &&
                <AgentRecallPanel
                  agent={agent}
                  onClose={() => setSelectedAgent(null)} />

                }
                </div>);

          })}
          </div>
        </div>
      }

      {/* Inactive agents */}
      {inactiveAgents.length > 0 &&
      <div>
          <div style={{ color: "#3f3f46", fontSize: 12, fontWeight: 600, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
            Inactive
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {safeMap(inactiveAgents, (agent) => {
            const ns = agent.memory_namespace || agent.name;
            const isSelected = selectedAgent === ns;
            return (
              <div key={agent.id || ns}>
                  <AgentCard
                  agent={agent}
                  isSelected={isSelected}
                  onSelect={() => setSelectedAgent(isSelected ? null : ns)} />

                  {isSelected &&
                <AgentRecallPanel
                  agent={agent}
                  onClose={() => setSelectedAgent(null)} />

                }
                </div>);

          })}
          </div>
        </div>
      }
    </div>);

}
