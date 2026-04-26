import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActionButton,
  EmptyState,
  ErrorState,
  InlineBadge,
  LoadingState,
  MetricCard,
  PageShell,
  SurfaceGrid,
  SurfacePanel,
  formatDateTime,
  surfacePalette,
} from "./SurfacePrimitives";
import { useAuth } from "../../context/AuthContext";
import { AdminAccessRequired } from "../shared/AdminApiErrorBoundary";
import {
  getCausalChain,
  getDropPointNarrative,
  getDropPointPrediction,
  getDropPointRecommendation,
  getLearningStats,
  getRippleTraceGraph,
} from "../../api/rippletrace.js";
import { safeMap } from "../../utils/safe";

function nodeTone(node) {
  if (!node) return "neutral";
  if (node.node_kind === "memory_node") return "info";
  const type = String(node.type || "").toLowerCase();
  if (type.includes("failed") || type.includes("error")) return "danger";
  if (type.includes("completed")) return "success";
  if (type.includes("started")) return "warning";
  return "neutral";
}

function edgeStroke(edge) {
  switch (edge.relationship_type) {
    case "memory_effect":
      return surfacePalette.info;
    case "async_child":
      return surfacePalette.warning;
    case "derived":
      return surfacePalette.accent;
    default:
      return "rgba(255,255,255,0.25)";
  }
}

function graphLayout(nodes, edges) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depthMap = new Map();
  const incoming = new Map();
  const outgoing = new Map();

  edges.forEach((edge) => {
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
    const list = outgoing.get(edge.source) || [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  });

  const queue = nodes.filter((node) => !incoming.get(node.id)).map((node) => ({ id: node.id, depth: 0 }));
  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    depthMap.set(current.id, Math.max(depthMap.get(current.id) || 0, current.depth));
    safeMap(outgoing.get(current.id) || [], (targetId) => {
      queue.push({ id: targetId, depth: current.depth + 1 });
    });
  }

  const grouped = new Map();
  nodes.forEach((node) => {
    const depth = depthMap.get(node.id) || 0;
    const group = grouped.get(depth) || [];
    group.push(node);
    grouped.set(depth, group);
  });

  const positioned = [];
  Array.from(grouped.entries())
    .sort((a, b) => a[0] - b[0])
    .forEach(([depth, group]) => {
      group.forEach((node, index) => {
        positioned.push({
          ...node,
          x: 140 + depth * 240,
          y: 80 + index * 110,
        });
      });
    });

  return {
    nodes: positioned,
    edges: edges.map((edge) => ({
      ...edge,
      sourceNode: positioned.find((node) => node.id === edge.source) || byId.get(edge.source),
      targetNode: positioned.find((node) => node.id === edge.target) || byId.get(edge.target),
    })),
  };
}

function TraceGraph({ nodes, edges, selectedNodeId, onSelectNode }) {
  const width = Math.max(960, (Math.max(...safeMap(nodes, (node) => node.x), 0) || 0) + 220);
  const height = Math.max(520, (Math.max(...safeMap(nodes, (node) => node.y), 0) || 0) + 140);

  return (
    <div className="overflow-auto rounded-[22px] border" style={{ borderColor: surfacePalette.border }}>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[560px] min-w-full bg-[rgba(4,17,13,0.24)]">
        {safeMap(edges, (edge) => {
          if (!edge.sourceNode || !edge.targetNode) return null;
          return (
            <g key={edge.id}>
              <line
                x1={edge.sourceNode.x}
                y1={edge.sourceNode.y}
                x2={edge.targetNode.x}
                y2={edge.targetNode.y}
                stroke={edgeStroke(edge)}
                strokeWidth={Math.max(1.5, Number(edge.weight || 1))}
                strokeOpacity="0.85"
              />
              <text
                x={(edge.sourceNode.x + edge.targetNode.x) / 2}
                y={(edge.sourceNode.y + edge.targetNode.y) / 2 - 6}
                textAnchor="middle"
                fontSize="10"
                fill={surfacePalette.muted}
              >
                {edge.relationship_type}
              </text>
            </g>
          );
        })}
        {safeMap(nodes, (node) => (
          <g
            key={node.id}
            transform={`translate(${node.x},${node.y})`}
            style={{ cursor: "pointer" }}
            onClick={() => onSelectNode(node.id)}
          >
            <circle
              r={node.node_kind === "memory_node" ? 20 : 24}
              fill={node.node_kind === "memory_node" ? "rgba(56,189,248,0.18)" : "rgba(0,255,170,0.14)"}
              stroke={selectedNodeId === node.id ? "#ffffff" : edgeStroke({ relationship_type: node.node_kind === "memory_node" ? "memory_effect" : "derived" })}
              strokeWidth={selectedNodeId === node.id ? 3 : 1.6}
            />
            <text x="0" y="-2" textAnchor="middle" fontSize="11" fontWeight="700" fill={surfacePalette.text}>
              {String(node.type || node.id).slice(0, 16)}
            </text>
            <text x="0" y="16" textAnchor="middle" fontSize="10" fill={surfacePalette.muted}>
              {node.node_kind}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export default function RippleTraceViewer() {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <AdminAccessRequired />;
  const [traceId, setTraceId] = useState("");
  const [submittedTraceId, setSubmittedTraceId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [activeTab, setActiveTab] = useState("graph");
  const [narrativeData, setNarrativeData] = useState(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [narrativeError, setNarrativeError] = useState("");
  const [predictionData, setPredictionData] = useState(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionError, setPredictionError] = useState("");
  const [learningStats, setLearningStats] = useState(null);
  const [learningLoading, setLearningLoading] = useState(false);
  const [learningError, setLearningError] = useState("");
  const [recommendationData, setRecommendationData] = useState(null);
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [causalChainData, setCausalChainData] = useState(null);
  const [causalChainOpen, setCausalChainOpen] = useState(false);
  const [causalChainLoading, setCausalChainLoading] = useState(false);
  const [causalChainError, setCausalChainError] = useState("");

  const loadTrace = useCallback(async (value) => {
    if (!value) return;
    setLoading(true);
    setError("");
    try {
      const graph = await getRippleTraceGraph(value);
      setData(graph);
      setSubmittedTraceId(value);
      setSelectedNodeId(graph.root_event?.id || graph.nodes?.[0]?.id || "");
      setActiveTab("graph");
      setNarrativeData(null);
      setPredictionData(null);
      setRecommendationData(null);
      setCausalChainData(null);
      setCausalChainOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ripple trace.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const graph = useMemo(() => {
    if (!data?.nodes?.length) return { nodes: [], edges: [] };
    return graphLayout(data.nodes, data.edges || []);
  }, [data]);

  const selectedNode = useMemo(
    () => graph.nodes.find((node) => node.id === selectedNodeId) || null,
    [graph.nodes, selectedNodeId],
  );

  useEffect(() => {
    if (submittedTraceId) {
      loadTrace(submittedTraceId);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const insights = data?.insights || {};
  const dropPointId = useMemo(() => {
    const nodes = data?.nodes || [];
    const match = nodes.find((node) => node?.payload?.drop_point_id);
    return match?.payload?.drop_point_id || "";
  }, [data]);

  const loadNarrative = useCallback(async () => {
    if (!dropPointId) return;
    setNarrativeLoading(true);
    setNarrativeError("");
    try {
      const narrative = await getDropPointNarrative(dropPointId);
      setNarrativeData(narrative);
    } catch (err) {
      setNarrativeError(err instanceof Error ? err.message : "Failed to load narrative.");
      setNarrativeData(null);
    } finally {
      setNarrativeLoading(false);
    }
  }, [dropPointId]);

  const loadPrediction = useCallback(async () => {
    if (!dropPointId) return;
    setPredictionLoading(true);
    setPredictionError("");
    try {
      const prediction = await getDropPointPrediction(dropPointId, false);
      setPredictionData(prediction);
    } catch (err) {
      setPredictionError(err instanceof Error ? err.message : "Failed to load predictions.");
      setPredictionData(null);
    } finally {
      setPredictionLoading(false);
    }
  }, [dropPointId]);

  const loadLearning = useCallback(async () => {
    setLearningLoading(true);
    setLearningError("");
    try {
      const stats = await getLearningStats();
      setLearningStats(stats);
    } catch (err) {
      setLearningError(err instanceof Error ? err.message : "Failed to load learning stats.");
      setLearningStats(null);
    } finally {
      setLearningLoading(false);
    }
  }, []);

  const loadRecommendation = useCallback(async () => {
    if (!dropPointId) return;
    setRecommendationLoading(true);
    setRecommendationError("");
    try {
      const recommendation = await getDropPointRecommendation(dropPointId);
      setRecommendationData(recommendation);
    } catch (err) {
      setRecommendationError(err instanceof Error ? err.message : "Failed to load recommendations.");
      setRecommendationData(null);
    } finally {
      setRecommendationLoading(false);
    }
  }, [dropPointId]);

  const loadCausalChain = useCallback(async () => {
    if (!dropPointId) return;
    setCausalChainLoading(true);
    setCausalChainError("");
    try {
      const chain = await getCausalChain(dropPointId);
      setCausalChainData(chain);
      setCausalChainOpen(true);
    } catch (err) {
      setCausalChainError(err instanceof Error ? err.message : "Failed to load causal chain.");
      setCausalChainData(null);
      setCausalChainOpen(true);
    } finally {
      setCausalChainLoading(false);
    }
  }, [dropPointId]);

  useEffect(() => {
    if (activeTab === "narrative" && dropPointId && !narrativeData && !narrativeLoading) {
      loadNarrative();
    }
  }, [activeTab, dropPointId, narrativeData, narrativeLoading, loadNarrative]);

  useEffect(() => {
    if (activeTab === "predictions") {
      if (dropPointId && !predictionData && !predictionLoading) {
        loadPrediction();
      }
      if (!learningStats && !learningLoading) {
        loadLearning();
      }
    }
  }, [
    activeTab,
    dropPointId,
    predictionData,
    predictionLoading,
    learningStats,
    learningLoading,
    loadPrediction,
    loadLearning,
  ]);

  useEffect(() => {
    if (activeTab === "recommendations" && dropPointId && !recommendationData && !recommendationLoading) {
      loadRecommendation();
    }
  }, [activeTab, dropPointId, recommendationData, recommendationLoading, loadRecommendation]);

  const tabButtonStyle = (tab) => ({
    color: activeTab === tab ? "#04110d" : surfacePalette.text,
    background: activeTab === tab ? surfacePalette.accent : "rgba(255,255,255,0.03)",
    borderColor: activeTab === tab ? "rgba(0,255,170,0.5)" : surfacePalette.border,
  });

  const narrativeTimeline = narrativeData?.timeline || [];
  const hiddenTimelineCount = Math.max(0, narrativeTimeline.length - 15);

  return (
    <PageShell
      eyebrow="Explainability"
      title="RippleTrace Proofboard"
      description="Visualize one execution trace as a causal graph, inspect root cause and dominant path, and review generated recommendations from the live SystemEvent ledger."
      actions={
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={traceId}
            onChange={(event) => setTraceId(event.target.value)}
            placeholder="Enter trace_id"
            className="rounded-full border px-4 py-2 text-sm outline-none"
            style={{
              color: surfacePalette.text,
              background: "rgba(255,255,255,0.03)",
              borderColor: surfacePalette.border,
            }}
          />
          <ActionButton onClick={() => loadTrace(traceId)}>Load Trace</ActionButton>
        </div>
      }
    >
      <SurfaceGrid>
        <div className="lg:col-span-8">
          <SurfacePanel title="Trace Graph" subtitle="Nodes are SystemEvents and memory artifacts. Edges show causal relationships across the trace.">
            {loading ? <LoadingState label="Loading ripple proofboard" /> : null}
            {!loading && error ? <ErrorState message={error} onRetry={() => loadTrace(submittedTraceId || traceId)} /> : null}
            {!loading && !error && !graph.nodes.length ? (
              <EmptyState
                title="No trace loaded"
                description="Provide a trace_id to inspect the execution graph, failure clusters, and dominant path."
              />
            ) : null}
            {!loading && !error && graph.nodes.length ? (
              <TraceGraph
                nodes={graph.nodes}
                edges={graph.edges}
                selectedNodeId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
              />
            ) : null}
          </SurfacePanel>

          {!loading && !error && data ? (
            <div className="mt-5">
              <div className="mb-5 flex flex-wrap items-center gap-2">
                {[
                  ["graph", "Graph"],
                  ["narrative", "Narrative"],
                  ["predictions", "Predictions"],
                  ["recommendations", "Recommendations"],
                ].map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className="rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] transition-all"
                    style={tabButtonStyle(tab)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {activeTab === "narrative" ? (
                <div className="space-y-5">
                  {!dropPointId ? (
                    <EmptyState
                      title="No drop point linked to this trace."
                      description="Narrative data is available for traces linked to a drop point."
                    />
                  ) : narrativeLoading ? (
                    <LoadingState label="Loading narrative..." />
                  ) : narrativeError ? (
                    <ErrorState message="Failed to load narrative." onRetry={loadNarrative} />
                  ) : narrativeData ? (
                    <>
                      <SurfacePanel title="Narrative Summary">
                        <p className="text-sm text-zinc-300">{narrativeData.summary}</p>
                      </SurfacePanel>
                      <SurfacePanel title="Timeline">
                        <ol className="space-y-3">
                          {safeMap(narrativeTimeline.slice(0, 15), (event, index) => (
                            <li key={`${event.timestamp || event.event}-${index}`} className="rounded-2xl border p-3" style={{ borderColor: surfacePalette.border }}>
                              <div className="text-sm text-zinc-300">
                                {formatDateTime(event.timestamp)} {"—"} {event.event}
                              </div>
                              {event.summary ? <div className="mt-1 text-sm text-zinc-400">{event.summary}</div> : null}
                            </li>
                          ))}
                        </ol>
                        {hiddenTimelineCount ? (
                          <div className="mt-3 text-sm text-zinc-500">[{hiddenTimelineCount} more events not shown]</div>
                        ) : null}
                      </SurfacePanel>
                      <SurfacePanel title="Inflection Points">
                        <div className="space-y-3">
                          {safeMap(narrativeData.inflection_points || [], (point, index) => (
                            <div key={`${point.type}-${index}`} className="flex flex-wrap items-center gap-3 text-sm text-zinc-300">
                              <InlineBadge>{point.type}</InlineBadge>
                              <span>{formatDateTime(point.timestamp)}</span>
                              <span>value: {String(point.value ?? "—")}</span>
                            </div>
                          ))}
                          {!(narrativeData.inflection_points || []).length ? (
                            <EmptyState title="No inflection points" description="This narrative does not yet have recorded inflection points." />
                          ) : null}
                        </div>
                      </SurfacePanel>
                      <SurfacePanel title="Causal Story">
                        <div className="grid gap-4 md:grid-cols-2">
                          <div>
                            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: surfacePalette.muted }}>
                              Influenced By
                            </div>
                            <div className="space-y-3">
                              {safeMap(narrativeData.causal_story?.influenced_by || [], (entry) => (
                                <div key={`in-${entry.drop_point_id}`} className="rounded-2xl border p-3 text-sm text-zinc-300" style={{ borderColor: surfacePalette.border }}>
                                  {entry.drop_point_id} {"—"} {(Number(entry.confidence || 0) * 100).toFixed(0)}%
                                </div>
                              ))}
                              {!(narrativeData.causal_story?.influenced_by || []).length ? (
                                <div className="text-sm text-zinc-500">No upstream influences.</div>
                              ) : null}
                            </div>
                          </div>
                          <div>
                            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: surfacePalette.muted }}>
                              Led To
                            </div>
                            <div className="space-y-3">
                              {safeMap(narrativeData.causal_story?.led_to || [], (entry) => (
                                <div key={`out-${entry.drop_point_id}`} className="rounded-2xl border p-3 text-sm text-zinc-300" style={{ borderColor: surfacePalette.border }}>
                                  {entry.drop_point_id} {"—"} {(Number(entry.confidence || 0) * 100).toFixed(0)}%
                                </div>
                              ))}
                              {!(narrativeData.causal_story?.led_to || []).length ? (
                                <div className="text-sm text-zinc-500">No downstream effects.</div>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </SurfacePanel>
                    </>
                  ) : null}
                </div>
              ) : null}

              {activeTab === "predictions" ? (
                <div className="space-y-5">
                  {!dropPointId ? (
                    <EmptyState
                      title="No drop point linked to this trace."
                      description="Prediction data is available for traces linked to a drop point."
                    />
                  ) : predictionLoading ? (
                    <LoadingState label="Loading prediction..." />
                  ) : predictionError ? (
                    <ErrorState message="Failed to load predictions." onRetry={loadPrediction} />
                  ) : predictionData?.status === "insufficient_data" ? (
                    <EmptyState
                      title="Not enough historical data for this drop point."
                      description="Predictions require at least 3 score snapshots."
                    />
                  ) : (
                    <>
                      <div className="grid gap-4 md:grid-cols-2">
                        <MetricCard
                          label="Prediction"
                          value={predictionData?.prediction || predictionData?.status || "—"}
                          tone="info"
                        />
                        <MetricCard
                          label="Confidence"
                          value={
                            predictionData?.confidence != null
                              ? `${(predictionData.confidence * 100).toFixed(0)}%`
                              : "—"
                          }
                          tone="warning"
                        />
                      </div>
                      <SurfacePanel title="Learning Stats">
                        {learningLoading ? (
                          <LoadingState label="Loading learning stats..." />
                        ) : learningError ? (
                          <ErrorState message="Failed to load learning stats." onRetry={loadLearning} />
                        ) : (
                          <div className="grid gap-4 md:grid-cols-3">
                            <MetricCard
                              label="Accuracy"
                              value={`${(Number(learningStats?.accuracy || 0) * 100).toFixed(0)}%`}
                              tone="success"
                            />
                            <MetricCard
                              label="Total Predictions"
                              value={learningStats?.total_predictions ?? 0}
                              tone="info"
                            />
                            <MetricCard
                              label="False Positives"
                              value={`${(Number(learningStats?.false_positive_rate || 0) * 100).toFixed(1)}%`}
                              tone="danger"
                            />
                          </div>
                        )}
                      </SurfacePanel>
                    </>
                  )}
                </div>
              ) : null}

              {activeTab === "recommendations" ? (
                <div className="space-y-5">
                  {!dropPointId ? (
                    <EmptyState
                      title="No drop point linked to this trace."
                      description="Recommendations are available for traces linked to a drop point."
                    />
                  ) : recommendationLoading ? (
                    <LoadingState label="Loading recommendations..." />
                  ) : recommendationError ? (
                    <ErrorState message="Failed to load recommendations." onRetry={loadRecommendation} />
                  ) : recommendationData ? (
                    <>
                      <SurfacePanel title="Recommended Action">
                        <InlineBadge
                          tone={
                            recommendationData.priority === "high"
                              ? "danger"
                              : recommendationData.priority === "medium"
                                ? "warning"
                                : "neutral"
                          }
                        >
                          {recommendationData.action}
                        </InlineBadge>
                      </SurfacePanel>
                      <SurfacePanel
                        title="Action Items"
                        actions={
                          <ActionButton tone="ghost" onClick={() => {
                            if (causalChainOpen) {
                              setCausalChainOpen(false);
                              return;
                            }
                            loadCausalChain();
                          }}
                          >
                            Get Causal Chain
                          </ActionButton>
                        }
                      >
                        <ul className="list-disc space-y-2 pl-5">
                          {safeMap(recommendationData.recommendations || [], (item, index) => (
                            <li key={`${item}-${index}`} className="text-sm text-zinc-300">
                              {item}
                            </li>
                          ))}
                        </ul>
                        {!(recommendationData.recommendations || []).length ? (
                          <EmptyState title="No actions available" description="No recommendation action items were returned." />
                        ) : null}

                        {causalChainOpen ? (
                          <div className="mt-5 border-t pt-5" style={{ borderColor: surfacePalette.border }}>
                            {causalChainLoading ? (
                              <LoadingState label="Loading causal chain..." />
                            ) : causalChainError ? (
                              <ErrorState message="Failed to load causal chain." onRetry={loadCausalChain} />
                            ) : causalChainData ? (
                              <div className="grid gap-4 md:grid-cols-2">
                                <div>
                                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: surfacePalette.muted }}>
                                    Upstream causes
                                  </div>
                                  <div className="space-y-3">
                                    {safeMap(causalChainData.upstream_causes || [], (entry) => (
                                      <div key={`up-${entry.drop_point_id}`} className="rounded-2xl border p-3 text-sm text-zinc-300" style={{ borderColor: surfacePalette.border }}>
                                        {entry.drop_point_id} {"—"} {(Number(entry.confidence || 0) * 100).toFixed(0)}%
                                      </div>
                                    ))}
                                    {!(causalChainData.upstream_causes || []).length ? (
                                      <div className="text-sm text-zinc-500">No upstream causes found.</div>
                                    ) : null}
                                  </div>
                                </div>
                                <div>
                                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: surfacePalette.muted }}>
                                    Downstream effects
                                  </div>
                                  <div className="space-y-3">
                                    {safeMap(causalChainData.downstream_effects || [], (entry) => (
                                      <div key={`down-${entry.drop_point_id}`} className="rounded-2xl border p-3 text-sm text-zinc-300" style={{ borderColor: surfacePalette.border }}>
                                        {entry.drop_point_id} {"—"} {(Number(entry.confidence || 0) * 100).toFixed(0)}%
                                      </div>
                                    ))}
                                    {!(causalChainData.downstream_effects || []).length ? (
                                      <div className="text-sm text-zinc-500">No downstream effects found.</div>
                                    ) : null}
                                  </div>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </SurfacePanel>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="lg:col-span-4" style={{ display: activeTab === "graph" ? undefined : "none" }}>
          <SurfacePanel title="Trace Summary" subtitle="Proofboard summary built from the current graph and causal analysis.">
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-1">
              <MetricCard label="Nodes" value={data?.ripple_span?.node_count || 0} tone="info" />
              <MetricCard label="Edges" value={data?.ripple_span?.edge_count || 0} tone="warning" />
              <MetricCard label="Depth" value={data?.ripple_span?.depth || 0} tone="neutral" />
              <MetricCard label="Terminal Events" value={data?.ripple_span?.terminal_count || 0} tone="danger" />
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {data?.root_event ? <InlineBadge tone={nodeTone(data.root_event)}>Root: {data.root_event.type}</InlineBadge> : null}
              {safeMap(data?.terminal_events || [], (event) => (
                <InlineBadge key={event.id} tone={nodeTone(event)}>
                  Terminal: {event.type}
                </InlineBadge>
              ))}
            </div>
            <p className="mt-5 text-sm leading-7" style={{ color: surfacePalette.text }}>
              {insights.summary || "No causal explanation available yet."}
            </p>
          </SurfacePanel>

          <SurfacePanel className="mt-5" title="Insights" subtitle="Root cause, dominant path, and failure clusters across this trace.">
            <div className="space-y-4 text-sm">
              <div>
                <div style={{ color: surfacePalette.muted }}>Root Cause</div>
                <div style={{ color: surfacePalette.text }}>
                  {insights.root_cause?.type || "No root cause identified"}
                </div>
              </div>

              <div>
                <div style={{ color: surfacePalette.muted }}>Dominant Path</div>
                <div style={{ color: surfacePalette.text }}>
                  {insights.dominant_path?.length
                    ? safeMap(insights.dominant_path, (node) => node.type).join(" -> ")
                    : "No dominant path identified"}
                </div>
              </div>

              <div>
                <div style={{ color: surfacePalette.muted }}>Failure Clusters</div>
                {safeMap(insights.failure_clusters || [], (cluster) => (
                  <div key={cluster.type} className="mt-2 rounded-2xl border p-3" style={{ borderColor: surfacePalette.border }}>
                    <div style={{ color: surfacePalette.text }}>{cluster.type}</div>
                    <div style={{ color: surfacePalette.muted }}>{cluster.count} events</div>
                  </div>
                ))}
                {!(insights.failure_clusters || []).length ? (
                  <div style={{ color: surfacePalette.text }}>No failure clusters detected.</div>
                ) : null}
              </div>
            </div>
          </SurfacePanel>

          <SurfacePanel className="mt-5" title="Recommendations" subtitle="Operational recommendations generated from the current causal structure.">
            <div className="space-y-3">
              {safeMap(insights.recommendations || [], (item, index) => (
                <div key={`${item}-${index}`} className="rounded-2xl border p-3 text-sm leading-6" style={{ borderColor: surfacePalette.border, color: surfacePalette.text }}>
                  {item}
                </div>
              ))}
              {!(insights.recommendations || []).length ? (
                <EmptyState title="No recommendations" description="Load a trace with causal activity to generate operational recommendations." />
              ) : null}
            </div>
          </SurfacePanel>

          <SurfacePanel className="mt-5" title="Selected Node" subtitle="Inspect the payload and metadata for the active node.">
            {selectedNode ? (
              <div className="space-y-3 text-sm">
                <InlineBadge tone={nodeTone(selectedNode)}>{selectedNode.type}</InlineBadge>
                <div style={{ color: surfacePalette.muted }}>Kind</div>
                <div style={{ color: surfacePalette.text }}>{selectedNode.node_kind}</div>
                <div style={{ color: surfacePalette.muted }}>Timestamp</div>
                <div style={{ color: surfacePalette.text }}>{formatDateTime(selectedNode.timestamp)}</div>
                <div style={{ color: surfacePalette.muted }}>Source</div>
                <div style={{ color: surfacePalette.text }}>{selectedNode.source || "unknown"}</div>
                <pre
                  className="overflow-auto rounded-2xl border p-3 text-xs leading-6"
                  style={{
                    borderColor: surfacePalette.border,
                    color: surfacePalette.text,
                    background: "rgba(255,255,255,0.02)",
                  }}
                >
                  {JSON.stringify(selectedNode.payload || {}, null, 2)}
                </pre>
              </div>
            ) : (
              <EmptyState title="Nothing selected" description="Select a graph node to inspect its payload." />
            )}
          </SurfacePanel>
        </div>
      </SurfaceGrid>
    </PageShell>
  );
}
