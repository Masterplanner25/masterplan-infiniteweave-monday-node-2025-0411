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
} from "./ops/SurfacePrimitives";
import { getRippleTraceGraph } from "../api";
import { safeMap } from "../utils/safe";

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
  const [traceId, setTraceId] = useState("");
  const [submittedTraceId, setSubmittedTraceId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");

  const loadTrace = useCallback(async (value) => {
    if (!value) return;
    setLoading(true);
    setError("");
    try {
      const graph = await getRippleTraceGraph(value);
      setData(graph);
      setSubmittedTraceId(value);
      setSelectedNodeId(graph.root_event?.id || graph.nodes?.[0]?.id || "");
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
        </div>

        <div className="lg:col-span-4">
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
