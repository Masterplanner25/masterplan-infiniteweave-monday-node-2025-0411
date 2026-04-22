import React, { useCallback, useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { getCausalGraph, getInfluenceGraph, getNarrative } from "../../api";import { safeMap } from "../../utils/safe";

const COLORS = {
  canvas: "#06070b",
  panel: "#07090f",
  accent: "#6cf",
  highlight: "#9ff",
  causal: "#7ff",
  text: "#e5e7eb",
  dim: "#9aa3b5",
  border: "#1e2530"
};

const MODE_LABELS = {
  influence: "Influence View",
  causal: "Causal View"
};

const formatTimestamp = (value) => {
  if (!value) return "Unknown time";
  const date = new Date(value);
  return date.toLocaleString();
};

export default function GraphView() {
  const svgRef = useRef(null);
  const [graphs, setGraphs] = useState({ influence: null, causal: null });
  const [mode, setMode] = useState("influence");
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [resizeTrigger, setResizeTrigger] = useState(0);
  const simulationRef = useRef(null);

  const fetchNarrativeForNode = useCallback(async (node) => {
    setNarrative(null);
    try {
      const payload = await getNarrative(node.id);
      setNarrative(payload);
    } catch (err) {
      setNarrative({ error: err.message || "Failed to load narrative." });
    }
  }, []);

  useEffect(() => {
    let active = true;
    const loadGraphs = async () => {
      try {
        const [influence, causal] = await Promise.all([
        getInfluenceGraph(),
        getCausalGraph()]
        );
        if (!active) return;
        setGraphs({ influence, causal });
        setStatus("ready");
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load graph data.");
        setStatus("error");
      }
    };
    loadGraphs();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setResizeTrigger((prev) => prev + 1);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (!graphs.influence?.nodes?.length) return;
    if (mode === "causal" && !graphs.causal?.causal_edges?.length) return;

    const svgEl = svgRef.current;
    if (!svgEl) return;

    const width = svgEl.clientWidth || 960;
    const height = svgEl.clientHeight || 520;

    if (simulationRef.current) {
      simulationRef.current.stop();
    }

    const svg = d3.
    select(svgEl).
    attr("viewBox", `0 0 ${width} ${height}`).
    attr("preserveAspectRatio", "xMidYMid meet");

    svg.selectAll("*").remove();

    const defs = svg.append("defs");
    defs.
    append("marker").
    attr("id", "causal-arrow").
    attr("viewBox", "0 -5 10 10").
    attr("refX", 18).
    attr("refY", 0).
    attr("markerWidth", 6).
    attr("markerHeight", 6).
    attr("orient", "auto").
    attr("fill", COLORS.causal).
    append("path").
    attr("d", "M0,-4L8,0L0,4");

    const canvas = svg.append("g");
    const linkLayer = canvas.append("g").attr("class", "links");
    const nodeLayer = canvas.append("g").attr("class", "nodes");

    const nodes = safeMap(graphs.influence.nodes, (node) => ({ ...node }));
    const rawEdges =
    mode === "causal" ? graphs.causal?.causal_edges ?? [] : graphs.influence.edges ?? [];
    const heavy = nodes.length > 100;
    const maxEdges = heavy ? Math.min(rawEdges.length, Math.floor(nodes.length * 1.4)) : rawEdges.length;
    const baseEdges = safeMap(rawEdges.
    slice(0, maxEdges),
    (edge) => ({
      ...edge,
      strength: Math.max(0.1, edge.strength ?? edge.confidence ?? 0.2)
    }));

    const maxScore = Math.max(...safeMap(nodes, (node) => node.narrative_score || 0), 1);
    const radiusScale = d3.scaleLinear().domain([0, maxScore]).range([6, 24]);
    const charge = heavy ? -30 : -80;
    const linkDistance = heavy ? 60 : 120;

    const simulation = d3.
    forceSimulation(nodes).
    force(
      "link",
      d3.
      forceLink(baseEdges).
      id((node) => node.id).
      distance(linkDistance).
      strength((edge) => Math.min(edge.strength, 1))
    ).
    force("charge", d3.forceManyBody().strength(charge)).
    force("center", d3.forceCenter(width / 2, height / 2)).
    force("collision", d3.forceCollide((node) => radiusScale(node.narrative_score || 0) + 6));
    simulationRef.current = simulation;

    linkLayer.
    selectAll("line").
    data(baseEdges, (edge) => `${edge.source}-${edge.target}-${edge.type}`).
    join("line").
    attr("stroke", mode === "causal" ? COLORS.causal : COLORS.accent).
    attr("stroke-width", (edge) =>
    mode === "causal" ? 1.6 + edge.strength * 2.5 : 0.6 + edge.strength
    ).
    attr("stroke-opacity", (edge) => Math.max(0.25, edge.strength)).
    attr("marker-end", mode === "causal" ? "url(#causal-arrow)" : null);

    const drag = d3.
    drag().
    on("start", (event, node) => {
      if (!event.active) {
        simulation.alphaTarget(0.2).restart();
      }
      node.fx = node.x;
      node.fy = node.y;
    }).
    on("drag", (event, node) => {
      node.fx = event.x;
      node.fy = event.y;
    }).
    on("end", (event, node) => {
      if (!event.active) {
        simulation.alphaTarget(0);
      }
      node.fx = null;
      node.fy = null;
    });

    const mergedNodes = nodeLayer.selectAll("circle").data(nodes, (node) => node.id);
    const nodeEnter = mergedNodes.
    enter().
    append("circle").
    attr("stroke", "rgba(255,255,255,0.25)").
    attr("stroke-width", 1.4).
    call(drag);

    nodeEnter.
    merge(mergedNodes).
    attr("fill", (node) =>
    selectedNode?.id === node.id ? COLORS.highlight : COLORS.accent
    ).
    attr("r", (node) => radiusScale(node.narrative_score || 0)).
    attr("cursor", "pointer").
    on("mouseenter", (_, node) => setHoveredNode(node)).
    on("mouseleave", () => setHoveredNode(null)).
    on("click", (_, node) => {
      setSelectedNode(node);
      fetchNarrativeForNode(node);
    });

    mergedNodes.exit().remove();

    simulation.on("tick", () => {
      linkLayer.
      selectAll("line").
      attr("x1", (edge) => edge.source.x).
      attr("y1", (edge) => edge.source.y).
      attr("x2", (edge) => edge.target.x).
      attr("y2", (edge) => edge.target.y);

      nodeLayer.
      selectAll("circle").
      attr("cx", (node) => node.x).
      attr("cy", (node) => node.y);
    });

    svg.call(
      d3.
      zoom().
      scaleExtent([0.4, 2.8]).
      on("zoom", (event) => canvas.attr("transform", event.transform))
    );

    return () => {
      simulation.stop();
    };
  }, [graphs, mode, selectedNode?.id, resizeTrigger, fetchNarrativeForNode]);

  const defaultMessage =
  status === "loading" ? "Loading graph..." : "Add DropPoints to see influence graph";
  const hasNodes = graphs.influence?.nodes?.length;
  const activeEdges =
  mode === "causal" ?
  graphs.causal?.causal_edges?.length ?
  graphs.causal.causal_edges :
  [] :
  graphs.influence?.edges ?? [];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 320px",
        gap: 16,
        color: COLORS.text,
        fontFamily: "Inter, system-ui, sans-serif"
      }}>

      <div
        style={{
          background: COLORS.canvas,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 16,
          padding: 16,
          boxShadow: "0 20px 45px rgba(0,0,0,0.35)",
          minHeight: 520
        }}>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 12
          }}>

          <div style={{ display: "flex", gap: 8 }}>
            {safeMap(Object.entries(MODE_LABELS), ([key, label]) =>
            <button
              key={key}
              onClick={() => setMode(key)}
              style={{
                padding: "4px 12px",
                borderRadius: 999,
                border: `1px solid ${mode === key ? COLORS.accent : "transparent"}`,
                background:
                mode === key ? "rgba(108,204,255,0.12)" : "transparent",
                color: mode === key ? COLORS.accent : COLORS.dim,
                fontSize: 12,
                cursor: "pointer"
              }}>

                {label}
              </button>)
            }
          </div>
          <div style={{ fontSize: 12, color: COLORS.dim }}>
            {hasNodes ?
            `${graphs.influence.nodes.length} nodes - ${activeEdges.length} connections` :
            defaultMessage}
          </div>
        </div>
        <div
          style={{
            borderRadius: 14,
            background:
            "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(0,0,0,0.5))",
            padding: 8,
            minHeight: 520,
            position: "relative"
          }}>

          {!hasNodes &&
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: COLORS.dim,
              fontSize: 14
            }}>

              {status === "error" ? error : defaultMessage}
            </div>
          }
          <svg
            ref={svgRef}
            style={{
              width: "100%",
              height: "100%",
              borderRadius: 14
            }} />

        </div>
        <div
          style={{
            marginTop: 10,
            fontSize: 12,
            color: COLORS.dim,
            minHeight: 24
          }}>

          {hoveredNode ?
          <span>
              {hoveredNode.title} - {hoveredNode.platform || "Unknown Platform"} - Narrative{" "}
              {(hoveredNode.narrative_score ?? 0).toFixed(1)}
            </span> :

          "Hover a node to inspect"
          }
        </div>
      </div>
      <div
        style={{
          background: COLORS.panel,
          borderRadius: 16,
          padding: 16,
          border: `1px solid ${COLORS.accent}20`,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          minHeight: 520
        }}>

        <h3 style={{ margin: 0, color: COLORS.accent }}>
          {selectedNode ? selectedNode.title : "Select a DropPoint"}
        </h3>
        <p style={{ margin: 0, fontSize: 13, color: COLORS.dim }}>
          {selectedNode ?
          `Platform: ${selectedNode.platform || "Unknown"}` :
          "Click any node to pull a narrative timeline and strategic insight."}
        </p>

        {selectedNode &&
        <div
          style={{
            background: "#131820",
            borderRadius: 12,
            padding: 12,
            border: `1px solid ${COLORS.accent}50`
          }}>

            <p style={{ margin: 0, fontSize: 12, color: COLORS.dim }}>
              Narrative Score: {(selectedNode.narrative_score ?? 0).toFixed(1)}
            </p>
            <p style={{ margin: 0, fontSize: 12, color: COLORS.dim }}>
              Platform: {selectedNode.platform || "-"}
            </p>
          </div>
        }

        {narrative ?
        <>
            <section>
              <p style={{ margin: 0, fontSize: 12, color: COLORS.dim }}>Timeline</p>
              <ul style={{ margin: "6px 0 0", paddingLeft: 16, fontSize: 12 }}>
                {safeMap(narrative.timeline?.slice(-6), (event, idx) =>
              <li key={`${event.event}-${idx}`}>
                    <strong>{event.event}</strong> - {formatTimestamp(event.timestamp)}
                    {event.details ? ` - ${event.details}` : ""}
                  </li>) ||
              <li>Timeline data unavailable.</li>}
              </ul>
            </section>

            <section>
              <p style={{ margin: "12px 0 4px", fontSize: 12, color: COLORS.dim }}>
                Interpretation
              </p>
              <p style={{ margin: 0, fontSize: 12 }}>
                Current state:{" "}
                <strong>{narrative.interpretation?.current_state || "unknown"}</strong>
              </p>
              <p style={{ margin: "4px 0 0", fontSize: 12 }}>{narrative.interpretation?.insight}</p>
              <p style={{ margin: "4px 0 0", fontSize: 12 }}>
                Recommended action:{" "}
                <em>{narrative.interpretation?.recommended_action || "Hold"}</em>
              </p>
            </section>

            <section>
              <p style={{ margin: "12px 0 4px", fontSize: 12, color: COLORS.dim }}>
                Inflection Points
              </p>
              <ul style={{ margin: "6px 0 0", paddingLeft: 16, fontSize: 12 }}>
                {safeMap(narrative.inflection_points, (point, idx) =>
              <li key={`${point.type}-${idx}`}>
                    <strong>{point.type}</strong> - {formatTimestamp(point.timestamp)} -{" "}
                    {point.value}
                  </li>) ||
              <li>No inflection points detected.</li>}
              </ul>
            </section>
          </> :

        selectedNode &&
        <p style={{ fontSize: 12, color: COLORS.dim, marginTop: 8 }}>
              Loading narrative...
            </p>

        }

        {narrative?.summary &&
        <section>
            <p style={{ margin: "12px 0 4px", fontSize: 12, color: COLORS.dim }}>Summary</p>
            <p style={{ margin: 0, fontSize: 12 }}>{narrative.summary}</p>
          </section>
        }
      </div>
    </div>);

}