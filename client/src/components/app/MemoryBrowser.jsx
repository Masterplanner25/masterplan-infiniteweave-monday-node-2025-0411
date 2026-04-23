// src/components/MemoryBrowser.jsx
import React, { useState, useEffect, useCallback } from "react";
import {
  recallMemory,
  getMemorySuggestions,
  recordMemoryFeedback,
  getNodePerformance,
  getNodeHistory,
  traverseMemory,
  getFederatedRecall,
  shareMemoryNode,
  getMemoryNodes,
} from "../../api/memory.js";
import { useSystem } from "../../context/SystemContext";

// ── Color helpers ──────────────────────────────────────────────────────────
import { safeMap } from "../../utils/safe";const resonanceColor = (score) => {
  if (score >= 0.7) return "#00ffaa";
  if (score >= 0.4) return "#ffd93d";
  return "#ff6b6b";
};

const NODE_TYPE_COLORS = {
  decision: "#a78bfa",
  outcome: "#00ffaa",
  insight: "#60a5fa",
  relationship: "#fb923c",
  analysis: "#f472b6",
  search: "#34d399",
  conversation: "#94a3b8"
};

const AGENT_ICONS = {
  arm: "🧠",
  genesis: "🌐",
  nodus: "⚡",
  leadgen: "🎯",
  sylva: "🔮",
  user: "👤"
};

const AGENT_COLORS = {
  arm: "#a78bfa",
  genesis: "#60a5fa",
  nodus: "#ffd93d",
  leadgen: "#34d399",
  sylva: "#94a3b8",
  user: "#00ffaa"
};

// ── Sub-components ─────────────────────────────────────────────────────────

function ResonanceBar({ score }) {
  const pct = Math.round((score || 0) * 100);
  const color = resonanceColor(score || 0);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: "#27272a", borderRadius: 4 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontSize: 11, color, minWidth: 34, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {pct}%
      </span>
    </div>);

}

function Badge({ label, color = "#27272a", textColor = "#a1a1aa", style = {} }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: 0.5,
      textTransform: "uppercase",
      background: color + "22",
      color: color,
      border: `1px solid ${color}44`,
      ...style
    }}>
      {label}
    </span>);

}

function NodeDetailPanel({ nodeId, onClose }) {
  const [perf, setPerf] = useState(null);
  const [hist, setHist] = useState(null);
  const [trav, setTrav] = useState(null);
  const [tab, setTab] = useState("performance");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (tab === "performance" && !perf) {
      setLoading(true);
      getNodePerformance(nodeId).
      then(setPerf).
      catch(() => {}).
      finally(() => setLoading(false));
    } else if (tab === "history" && !hist) {
      setLoading(true);
      getNodeHistory(nodeId, 10).
      then((d) => setHist(d.history || [])).
      catch(() => setHist([])).
      finally(() => setLoading(false));
    } else if (tab === "traverse" && !trav) {
      setLoading(true);
      traverseMemory(nodeId, 2).
      then(setTrav).
      catch(() => setTrav({ nodes: [] })).
      finally(() => setLoading(false));
    }
  }, [tab, nodeId, perf, hist, trav]);

  const tabs = ["performance", "history", "traverse"];

  return (
    <div style={{ background: "#111113", border: "1px solid #27272a", borderRadius: 10, padding: 16, marginTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {safeMap(tabs, (t) =>
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "4px 12px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 11,
            fontWeight: tab === t ? 700 : 400,
            background: tab === t ? "#00ffaa22" : "transparent",
            color: tab === t ? "#00ffaa" : "#71717a"
          }}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>)
          }
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "#52525b", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>×</button>
      </div>

      {loading && <div style={{ color: "#52525b", fontSize: 12, padding: "12px 0" }}>Loading…</div>}

      {!loading && tab === "performance" && perf &&
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {safeMap([
        ["Success Count", perf.performance?.success_count ?? 0],
        ["Failure Count", perf.performance?.failure_count ?? 0],
        ["Usage Count", perf.performance?.usage_count ?? 0],
        ["Success Rate", `${Math.round((perf.performance?.success_rate ?? 0) * 100)}%`],
        ["Adaptive Weight", perf.performance?.adaptive_weight ?? "1.000"],
        ["Graph Links", perf.performance?.graph_connectivity?.toFixed(3) ?? "0.000"]],
        ([k, v]) =>
        <div key={k} style={{ background: "#18181b", borderRadius: 6, padding: "8px 12px" }}>
              <div style={{ fontSize: 10, color: "#52525b", marginBottom: 2 }}>{k}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#e4e4e7" }}>{v}</div>
            </div>)
        }
        </div>
      }

      {!loading && tab === "history" && (
      hist && hist.length > 0 ?
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {safeMap(hist, (h, i) =>
        <div key={i} style={{ background: "#18181b", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#a1a1aa" }}>
                <span style={{ color: "#52525b", marginRight: 8 }}>{new Date(h.changed_at || h.created_at).toLocaleDateString()}</span>
                <span style={{ color: "#e4e4e7" }}>{h.change_type || "updated"}</span>
                {h.content_before && <div style={{ marginTop: 4, color: "#52525b" }}>← {(h.content_before || "").slice(0, 80)}…</div>}
              </div>)
        }
          </div> :
      <div style={{ color: "#52525b", fontSize: 12 }}>No change history yet.</div>)
      }

      {!loading && tab === "traverse" && (
      trav && (trav.nodes || trav.connected_nodes || []).length > 0 ?
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {safeMap(trav.nodes || trav.connected_nodes || [], (n, i) =>
        <div key={i} style={{ background: "#18181b", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#a1a1aa" }}>
                <Badge label={n.node_type || "node"} color={NODE_TYPE_COLORS[n.node_type] || "#52525b"} style={{ marginRight: 6 }} />
                {(n.content || "").slice(0, 100)}
              </div>)
        }
          </div> :
      <div style={{ color: "#52525b", fontSize: 12 }}>No connected nodes found.</div>)
      }
    </div>);

}

function MemoryNodeCard({ node, agentFilter }) {
  const [expanded, setExpanded] = useState(false);
  const [feedback, setFeedback] = useState(null); // "success" | "failure" | null
  const [sharing, setSharing] = useState(false);
  const [isShared, setIsShared] = useState(node.is_shared);

  const score = node.resonance_score ?? node.score ?? 0;
  const agentNs = node.source_agent || "user";
  const color = NODE_TYPE_COLORS[node.node_type] || "#52525b";
  const agentColor = AGENT_COLORS[agentNs] || "#52525b";

  const handleFeedback = async (outcome) => {
    setFeedback(outcome); // optimistic
    try {
      await recordMemoryFeedback(node.id || node.node_id, outcome);
    } catch {

      // silent — feedback is fire-and-forget
    }};

  const handleShare = async () => {
    if (isShared) return;
    setSharing(true);
    try {
      await shareMemoryNode(node.id || node.node_id);
      setIsShared(true);
    } catch {

      // silent
    } finally {setSharing(false);
    }
  };

  const tags = node.tags || [];
  const createdAt = node.created_at ? new Date(node.created_at).toLocaleDateString() : "";

  return (
    <div style={{
      background: "#111113",
      border: "1px solid #27272a",
      borderRadius: 10,
      padding: "14px 16px",
      marginBottom: 8,
      transition: "border-color 0.2s"
    }}
    onMouseEnter={(e) => e.currentTarget.style.borderColor = "#3f3f46"}
    onMouseLeave={(e) => e.currentTarget.style.borderColor = "#27272a"}>

      {/* Top row: badges + share/privacy */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
        {node.node_type && <Badge label={node.node_type} color={color} />}
        <Badge
          label={`${AGENT_ICONS[agentNs] || "●"} ${agentNs}`}
          color={agentColor} />

        {isShared ?
        <Badge label="🌐 shared" color="#00ffaa" /> :
        <Badge label="🔒 private" color="#52525b" />}
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#52525b" }}>{createdAt}</span>
      </div>

      {/* Content preview */}
      <p style={{ margin: "0 0 10px", fontSize: 13, color: "#d4d4d8", lineHeight: 1.6 }}>
        {expanded ?
        node.content || "" :
        (node.content || "").slice(0, 150) + ((node.content || "").length > 150 ? "…" : "")}
      </p>

      {/* Tags */}
      {tags.length > 0 &&
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 10 }}>
          {safeMap(tags, (t) =>
        <span key={t} style={{ fontSize: 10, color: "#71717a", background: "#18181b", padding: "2px 6px", borderRadius: 3 }}>
              #{t}
            </span>)
        }
        </div>
      }

      {/* Resonance bar */}
      {score > 0 &&
      <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: "#52525b", marginBottom: 4 }}>Resonance Score</div>
          <ResonanceBar score={score} />
        </div>
      }

      {/* Meta row */}
      <div style={{ display: "flex", gap: 12, fontSize: 11, color: "#52525b", marginBottom: 10 }}>
        {node.usage_count != null && <span>Used {node.usage_count}×</span>}
        {node.weight != null && <span>Weight {node.weight.toFixed(2)}</span>}
      </div>

      {/* Action row */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {/* Feedback buttons */}
        <button
          onClick={() => handleFeedback("success")}
          title="This memory helped"
          style={{
            background: feedback === "success" ? "#00ffaa22" : "transparent",
            border: `1px solid ${feedback === "success" ? "#00ffaa" : "#27272a"}`,
            color: feedback === "success" ? "#00ffaa" : "#52525b",
            borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 13
          }}>
          👍</button>
        <button
          onClick={() => handleFeedback("failure")}
          title="This memory misled"
          style={{
            background: feedback === "failure" ? "#ff6b6b22" : "transparent",
            border: `1px solid ${feedback === "failure" ? "#ff6b6b" : "#27272a"}`,
            color: feedback === "failure" ? "#ff6b6b" : "#52525b",
            borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 13
          }}>
          👎</button>

        {!isShared &&
        <button
          onClick={handleShare}
          disabled={sharing}
          title="Share with all agents"
          style={{
            background: "transparent", border: "1px solid #27272a",
            color: "#52525b", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11
          }}>

            {sharing ? "Sharing…" : "🌐 Share"}
          </button>
        }

        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            marginLeft: "auto", background: "transparent", border: "1px solid #27272a",
            color: "#71717a", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11
          }}>

          {expanded ? "Collapse ▲" : "Expand ▼"}
        </button>
      </div>

      {/* Expanded detail panel */}
      {expanded && <NodeDetailPanel nodeId={node.id || node.node_id} onClose={() => setExpanded(false)} />}
    </div>);

}

function SuggestionCard({ suggestion }) {
  const conf = Math.round((suggestion.confidence || 0) * 100);
  const color = conf >= 70 ? "#00ffaa" : conf >= 40 ? "#ffd93d" : "#ff6b6b";
  return (
    <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, padding: "12px 14px", marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
        <div style={{ fontSize: 13, color: "#e4e4e7", fontWeight: 600 }}>{suggestion.action || suggestion.suggestion || "Suggestion"}</div>
        <span style={{ fontSize: 11, color, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>{conf}% confident</span>
      </div>
      {suggestion.reasoning &&
      <div style={{ fontSize: 12, color: "#71717a", lineHeight: 1.5, marginBottom: 6 }}>{suggestion.reasoning}</div>
      }
      {suggestion.warning &&
      <div style={{ fontSize: 11, color: "#ffd93d", marginTop: 4 }}>⚠ {suggestion.warning}</div>
      }
    </div>);

}

// ── Main component ─────────────────────────────────────────────────────────

const AGENTS = ["all", "arm", "genesis", "nodus", "leadgen", "user"];

export default function MemoryBrowser() {
  const { system } = useSystem();
  const [query, setQuery] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [nodes, setNodes] = useState(system?.memory || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [totalCount, setTotalCount] = useState(null);

  const [suggestions, setSuggestions] = useState([]);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestLoading, setSuggestLoading] = useState(false);

  // Load recent nodes on mount
  useEffect(() => {
    loadRecent();
  }, []);

  useEffect(() => {
    if ((system?.memory || []).length > 0) {
      setNodes(system.memory);
      setTotalCount(system.system_state?.memory_count ?? system.memory.length);
    }
  }, [system]);

  const loadRecent = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryNodes([], 20);
      // getMemoryNodes returns an array or {nodes, count}
      const nodeList = Array.isArray(data) ? data : data.nodes || data.results || [];
      setNodes(nodeList);
      setTotalCount(typeof data === "object" && !Array.isArray(data) ? data.count || nodeList.length : nodeList.length);
    } catch (e) {
      setError(String(e));
      setNodes([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = useCallback(async () => {
    if (!query.trim() && !tagInput.trim()) {
      await loadRecent();
      return;
    }
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const tags = safeMap(tagInput.split(","), (t) => t.trim()).filter(Boolean);
      const data = await recallMemory(query, tags, 20, false);
      const nodeList = data.results || [];
      setNodes(nodeList);
      setTotalCount(data.count || nodeList.length);
    } catch (e) {
      setError(String(e));
      setNodes([]);
    } finally {
      setLoading(false);
    }
  }, [query, tagInput]);

  const handleSuggest = async () => {
    if (!query.trim() && !tagInput.trim()) return;
    setSuggestLoading(true);
    setSuggestOpen(true);
    try {
      const tags = safeMap(tagInput.split(","), (t) => t.trim()).filter(Boolean);
      const data = await getMemorySuggestions(query, tags, 5);
      setSuggestions(data.suggestions || data.results || []);
    } catch {
      setSuggestions([]);
    } finally {
      setSuggestLoading(false);
    }
  };

  // Client-side agent filter
  const visibleNodes = agentFilter === "all" ?
  nodes :
  nodes.filter((n) => (n.source_agent || "user") === agentFilter);

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "2rem", color: "#e4e4e7", fontFamily: "sans-serif" }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: "#fff", letterSpacing: -0.5 }}>
          🧠 Memory Browser
        </h1>
        <div style={{ marginTop: 4, fontSize: 13, color: "#71717a" }}>
          What A.I.N.D.Y. has learned from your work
          {totalCount != null &&
          <span style={{ marginLeft: 8, color: "#00ffaa", fontWeight: 700 }}>
              · {totalCount} node{totalCount !== 1 ? "s" : ""}
            </span>
          }
        </div>
      </div>

      {/* Search bar */}
      <div style={{ background: "#111113", border: "1px solid #27272a", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search your memory… (e.g. 'Python architecture decisions')"
            style={{
              flex: 1, padding: "10px 14px", background: "#0c0c0e", border: "1px solid #27272a",
              borderRadius: 8, color: "#e4e4e7", fontSize: 13, outline: "none"
            }} />

          <button
            onClick={handleSearch}
            disabled={loading}
            style={{
              padding: "10px 20px", background: loading ? "#27272a" : "#00ffaa",
              color: loading ? "#71717a" : "#000", border: "none", borderRadius: 8,
              fontWeight: 700, cursor: loading ? "not-allowed" : "pointer", fontSize: 13
            }}>

            {loading ? "Searching…" : "Search"}
          </button>
          <button
            onClick={handleSuggest}
            disabled={suggestLoading}
            title="Get suggestions based on past memories"
            style={{
              padding: "10px 14px", background: "transparent",
              border: "1px solid #27272a", color: "#71717a",
              borderRadius: 8, cursor: "pointer", fontSize: 13
            }}>

            💡 Suggest
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="text"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            placeholder="Filter by tags (comma-separated)"
            style={{
              flex: 1, padding: "7px 12px", background: "#0c0c0e", border: "1px solid #27272a",
              borderRadius: 6, color: "#a1a1aa", fontSize: 12, outline: "none"
            }} />

          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            style={{
              padding: "7px 10px", background: "#0c0c0e", border: "1px solid #27272a",
              borderRadius: 6, color: "#a1a1aa", fontSize: 12, cursor: "pointer"
            }}>

            {safeMap(AGENTS, (a) =>
            <option key={a} value={a}>
                {a === "all" ? "All agents" : `${AGENT_ICONS[a] || ""} ${a}`}
              </option>)
            }
          </select>
          <button
            onClick={loadRecent}
            title="Load recent nodes"
            style={{
              padding: "7px 12px", background: "transparent",
              border: "1px solid #27272a", color: "#52525b",
              borderRadius: 6, cursor: "pointer", fontSize: 12
            }}>

            ↺ Recent
          </button>
        </div>
      </div>

      {/* Suggestions panel */}
      {suggestOpen &&
      <div style={{ background: "#111113", border: "1px solid #ffd93d44", borderRadius: 10, padding: 14, marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#ffd93d" }}>💡 Suggestions from past patterns</div>
            <button onClick={() => setSuggestOpen(false)} style={{ background: "none", border: "none", color: "#52525b", cursor: "pointer", fontSize: 16 }}>×</button>
          </div>
          {suggestLoading && <div style={{ color: "#52525b", fontSize: 12 }}>Analyzing past outcomes…</div>}
          {!suggestLoading && suggestions.length === 0 &&
        <div style={{ color: "#52525b", fontSize: 12 }}>No suggestions yet. Complete more tasks to build memory patterns.</div>
        }
          {!suggestLoading && safeMap(suggestions, (s, i) => <SuggestionCard key={i} suggestion={s} />)}
        </div>
      }

      {/* Error */}
      {error &&
      <div style={{ background: "#2d1515", border: "1px solid #ff6b6b44", borderRadius: 8, padding: 12, marginBottom: 14, color: "#ff6b6b", fontSize: 13 }}>
          <strong>Error:</strong> {error}
        </div>
      }

      {/* Results */}
      {!loading && visibleNodes.length === 0 &&
      <div style={{ textAlign: "center", padding: "48px 24px", background: "#111113", border: "1px solid #27272a", borderRadius: 12 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🧠</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#e4e4e7", marginBottom: 8 }}>
            {hasSearched ? "No memories match your search" : "Your memory is empty"}
          </div>
          <div style={{ fontSize: 13, color: "#71717a", maxWidth: 380, margin: "0 auto", lineHeight: 1.6 }}>
            {hasSearched ?
          "Try different keywords, fewer tags, or switch to 'All agents' to widen the search." :
          "Use ARM to analyze code, Genesis to build a masterplan, or complete Tasks — A.I.N.D.Y. captures each event as a memory node automatically."}
          </div>
        </div>
      }

      {!loading && visibleNodes.length > 0 &&
      <div>
          <div style={{ fontSize: 11, color: "#52525b", marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
            {visibleNodes.length} result{visibleNodes.length !== 1 ? "s" : ""}
            {agentFilter !== "all" && ` from ${agentFilter}`}
          </div>
          {safeMap(visibleNodes, (node, i) =>
        <MemoryNodeCard key={node.id || node.node_id || i} node={node} agentFilter={agentFilter} />)
        }
        </div>
      }

      {loading &&
      <div style={{ textAlign: "center", padding: 40, color: "#52525b", fontSize: 13 }}>
          Scanning memory…
        </div>
      }
    </div>);

}
