import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";

import {
  getRecentRippleEvents,
  getRippleDropPoints,
  getRipplePings,
} from "../api";
import {
  ActionButton,
  EmptyState,
  ErrorState,
  formatDateTime,
  InlineBadge,
  LoadingState,
  PageShell,
  SurfaceGrid,
  SurfacePanel,
  surfacePalette,
} from "./ops/SurfacePrimitives";

function splitList(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string") return [];
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function includesFilter(value, filter) {
  if (!filter) return true;
  return String(value || "").toLowerCase().includes(filter.toLowerCase());
}

function toNodeColor(type) {
  if (type === "drop") return surfacePalette.accent;
  if (type === "recent") return surfacePalette.warning;
  return surfacePalette.info;
}

function GraphCanvas({ nodes, links, selectedNodeId, onSelectNode }) {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current) return undefined;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 960;
    const height = 560;
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const root = svg.append("g");
    const linkGroup = root.append("g");
    const nodeGroup = root.append("g");

    const zoom = d3
      .zoom()
      .scaleExtent([0.5, 3])
      .on("zoom", (event) => {
        root.attr("transform", event.transform);
      });

    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity.translate(width * 0.12, height * 0.1).scale(0.9));

    const simulationNodes = nodes.map((node) => ({ ...node }));
    const simulationLinks = links.map((link) => ({ ...link }));

    const simulation = d3
      .forceSimulation(simulationNodes)
      .force(
        "link",
        d3.forceLink(simulationLinks)
          .id((node) => node.id)
          .distance((link) => (link.kind === "ping" ? 110 : 150))
      )
      .force("charge", d3.forceManyBody().strength(-420))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius((node) => (node.type === "drop" ? 48 : 34)));

    const linkSelection = linkGroup
      .selectAll("line")
      .data(simulationLinks)
      .enter()
      .append("line")
      .attr("stroke", (link) => (link.kind === "recent" ? surfacePalette.warning : "rgba(255,255,255,0.18)"))
      .attr("stroke-width", (link) => Math.max(1.5, Number(link.strength || 1) * 1.8))
      .attr("stroke-opacity", 0.8);

    const nodeSelection = nodeGroup
      .selectAll("g")
      .data(simulationNodes)
      .enter()
      .append("g")
      .attr("data-node-id", (node) => node.id)
      .style("cursor", "pointer")
      .call(
        d3.drag()
          .on("start", (event, node) => {
            if (!event.active) simulation.alphaTarget(0.2).restart();
            node.fx = node.x;
            node.fy = node.y;
          })
          .on("drag", (event, node) => {
            node.fx = event.x;
            node.fy = event.y;
          })
          .on("end", (event, node) => {
            if (!event.active) simulation.alphaTarget(0);
            node.fx = null;
            node.fy = null;
          })
      )
      .on("click", (_, node) => onSelectNode(node.id));

    nodeSelection
      .append("circle")
      .attr("r", (node) => (node.type === "drop" ? 22 : 14))
      .attr("fill", (node) => toNodeColor(node.type))
      .attr("stroke", (node) => (
        node.id === selectedNodeId
          ? "#ffffff"
          : node.type === "drop"
          ? "rgba(0,255,170,0.45)"
          : "rgba(255,255,255,0.14)"
      ))
      .attr("stroke-width", (node) => (node.id === selectedNodeId ? 3 : 1.5));

    nodeSelection
      .append("text")
      .text((node) => node.label)
      .attr("fill", surfacePalette.text)
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("text-anchor", "middle")
      .attr("dy", (node) => (node.type === "drop" ? 38 : 28));

    simulation.on("tick", () => {
      linkSelection
        .attr("x1", (link) => link.source.x)
        .attr("y1", (link) => link.source.y)
        .attr("x2", (link) => link.target.x)
        .attr("y2", (link) => link.target.y);

      nodeSelection.attr("transform", (node) => `translate(${node.x},${node.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [links, nodes, onSelectNode]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("g[data-node-id] circle")
      .attr("stroke", function updateStroke() {
        const nodeId = d3.select(this.parentNode).attr("data-node-id");
        const node = nodes.find((item) => item.id === nodeId);
        if (!node) return "rgba(255,255,255,0.14)";
        if (node.id === selectedNodeId) return "#ffffff";
        return node.type === "drop" ? "rgba(0,255,170,0.45)" : "rgba(255,255,255,0.14)";
      })
      .attr("stroke-width", function updateStrokeWidth() {
        const nodeId = d3.select(this.parentNode).attr("data-node-id");
        return nodeId === selectedNodeId ? 3 : 1.5;
      });
  }, [nodes, selectedNodeId]);

  return (
    <div className="overflow-hidden rounded-[22px] border" style={{ borderColor: surfacePalette.border }}>
      <svg ref={svgRef} className="h-[560px] w-full bg-[rgba(4,17,13,0.24)]" />
    </div>
  );
}

export default function RippleTraceViewer() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessionFilter, setSessionFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [dropPoints, pings, recent] = await Promise.all([
        getRippleDropPoints(),
        getRipplePings(),
        getRecentRippleEvents(20),
      ]);
      setData({
        dropPoints: Array.isArray(dropPoints) ? dropPoints : [],
        pings: Array.isArray(pings) ? pings : [],
        recent: Array.isArray(recent) ? recent : [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ripple trace.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filtered = useMemo(() => {
    const dropPoints = (data?.dropPoints || []).filter((drop) => {
      const sessionSpace = [
        drop.id,
        drop.title,
        drop.intent,
        ...splitList(drop.core_themes),
        ...splitList(drop.tagged_entities),
      ].join(" ");
      const agentSpace = [drop.platform, drop.intent, ...splitList(drop.tagged_entities)].join(" ");
      return includesFilter(sessionSpace, sessionFilter) && includesFilter(agentSpace, agentFilter);
    });

    const dropPointIds = new Set(dropPoints.map((drop) => drop.id));

    const pings = (data?.pings || []).filter((ping) => {
      const sessionSpace = [
        ping.drop_point_id,
        ping.connection_summary,
        ping.reaction_notes,
        ping.external_url,
      ].join(" ");
      const agentSpace = [ping.source_platform, ping.ping_type, ping.connection_type].join(" ");
      const passes = includesFilter(sessionSpace, sessionFilter) && includesFilter(agentSpace, agentFilter);
      return passes && dropPointIds.has(ping.drop_point_id);
    });

    return { dropPoints, pings };
  }, [agentFilter, data, sessionFilter]);

  const graph = useMemo(() => {
    const nodes = [];
    const links = [];
    const recentIds = new Set((data?.recent || []).map((ping) => ping.id));

    filtered.dropPoints.forEach((drop) => {
      nodes.push({
        id: drop.id,
        label: drop.title?.slice(0, 18) || drop.id,
        type: "drop",
        raw: drop,
      });
    });

    filtered.pings.forEach((ping) => {
      const nodeId = `ping:${ping.id}`;
      nodes.push({
        id: nodeId,
        label: ping.ping_type?.slice(0, 18) || ping.id,
        type: recentIds.has(ping.id) ? "recent" : "ping",
        raw: ping,
      });
      links.push({
        source: ping.drop_point_id,
        target: nodeId,
        kind: recentIds.has(ping.id) ? "recent" : "ping",
        strength: ping.strength || 1,
      });
    });

    return { nodes, links };
  }, [data, filtered]);

  useEffect(() => {
    if (!selectedNodeId && graph.nodes.length) {
      setSelectedNodeId(graph.nodes[0].id);
      return;
    }
    if (selectedNodeId && !graph.nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(graph.nodes[0]?.id || "");
    }
  }, [graph.nodes, selectedNodeId]);

  const selectedNode = useMemo(
    () => graph.nodes.find((node) => node.id === selectedNodeId) || null,
    [graph.nodes, selectedNodeId]
  );

  return (
    <PageShell
      eyebrow="Causal Mapping"
      title="Ripple Trace Viewer"
      description="Explore drop points and downstream pings as a navigable causal graph. Session and agent filters are applied client-side against the available trace metadata because the current API does not expose dedicated graph filters."
      actions={<ActionButton tone="ghost" onClick={loadData}>Refresh Graph</ActionButton>}
    >
      <SurfaceGrid>
        <div className="lg:col-span-3">
          <SurfacePanel title="Graph Filters" subtitle="Zoom, pan, and narrow the graph using the metadata currently available from RippleTrace.">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
              Session Filter
            </label>
            <input
              value={sessionFilter}
              onChange={(event) => setSessionFilter(event.target.value)}
              placeholder="Drop id, title, theme, note..."
              className="mt-2 w-full rounded-2xl border px-4 py-3 text-sm outline-none"
              style={{
                color: surfacePalette.text,
                background: "rgba(255,255,255,0.03)",
                borderColor: surfacePalette.border,
              }}
            />

            <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
              Agent Filter
            </label>
            <input
              value={agentFilter}
              onChange={(event) => setAgentFilter(event.target.value)}
              placeholder="Platform, ping type, connection..."
              className="mt-2 w-full rounded-2xl border px-4 py-3 text-sm outline-none"
              style={{
                color: surfacePalette.text,
                background: "rgba(255,255,255,0.03)",
                borderColor: surfacePalette.border,
              }}
            />

            <div className="mt-5 flex flex-wrap gap-2">
              <InlineBadge tone="success">{filtered.dropPoints.length} drop points</InlineBadge>
              <InlineBadge tone="info">{filtered.pings.length} pings</InlineBadge>
              <InlineBadge tone="warning">{graph.links.length} causal links</InlineBadge>
            </div>
          </SurfacePanel>

          <SurfacePanel
            className="mt-5"
            title="Selection Details"
            subtitle="Click any node in the graph to inspect its payload."
          >
            {selectedNode ? (
              <div className="space-y-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <InlineBadge tone={selectedNode.type === "drop" ? "success" : selectedNode.type === "recent" ? "warning" : "info"}>
                    {selectedNode.type}
                  </InlineBadge>
                  <span className="font-semibold" style={{ color: surfacePalette.text }}>
                    {selectedNode.raw?.title || selectedNode.raw?.ping_type || selectedNode.id}
                  </span>
                </div>
                {"platform" in (selectedNode.raw || {}) ? (
                  <div style={{ color: surfacePalette.muted }}>
                    Platform: <span style={{ color: surfacePalette.text }}>{selectedNode.raw.platform}</span>
                  </div>
                ) : null}
                {"source_platform" in (selectedNode.raw || {}) ? (
                  <div style={{ color: surfacePalette.muted }}>
                    Source: <span style={{ color: surfacePalette.text }}>{selectedNode.raw.source_platform}</span>
                  </div>
                ) : null}
                {"intent" in (selectedNode.raw || {}) ? (
                  <div style={{ color: surfacePalette.muted }}>
                    Intent: <span style={{ color: surfacePalette.text }}>{selectedNode.raw.intent}</span>
                  </div>
                ) : null}
                {"date_dropped" in (selectedNode.raw || {}) ? (
                  <div style={{ color: surfacePalette.muted }}>
                    Dropped: <span style={{ color: surfacePalette.text }}>{formatDateTime(selectedNode.raw.date_dropped)}</span>
                  </div>
                ) : null}
                {"date_detected" in (selectedNode.raw || {}) ? (
                  <div style={{ color: surfacePalette.muted }}>
                    Detected: <span style={{ color: surfacePalette.text }}>{formatDateTime(selectedNode.raw.date_detected)}</span>
                  </div>
                ) : null}
                {"connection_summary" in (selectedNode.raw || {}) && selectedNode.raw.connection_summary ? (
                  <p className="rounded-2xl border p-3 leading-7" style={{ borderColor: surfacePalette.border, color: surfacePalette.text }}>
                    {selectedNode.raw.connection_summary}
                  </p>
                ) : null}
                {"reaction_notes" in (selectedNode.raw || {}) && selectedNode.raw.reaction_notes ? (
                  <p className="rounded-2xl border p-3 leading-7" style={{ borderColor: surfacePalette.border, color: surfacePalette.text }}>
                    {selectedNode.raw.reaction_notes}
                  </p>
                ) : null}
              </div>
            ) : (
              <EmptyState
                title="Nothing selected"
                description="Select a node in the graph to inspect the trace details."
              />
            )}
          </SurfacePanel>
        </div>

        <div className="lg:col-span-9">
          <SurfacePanel
            title="Causal Graph"
            subtitle="Drag nodes to inspect clusters. Mouse wheel zoom and canvas pan are enabled."
          >
            {loading ? <LoadingState label="Loading ripple trace" /> : null}
            {!loading && error ? <ErrorState message={error} onRetry={loadData} /> : null}
            {!loading && !error && !graph.nodes.length ? (
              <EmptyState
                title="No ripple trace data"
                description="Drop points and pings will appear here once RippleTrace has recorded activity."
              />
            ) : null}
            {!loading && !error && graph.nodes.length ? (
              <GraphCanvas
                nodes={graph.nodes}
                links={graph.links}
                selectedNodeId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
              />
            ) : null}
          </SurfacePanel>
        </div>
      </SurfaceGrid>
    </PageShell>
  );
}
