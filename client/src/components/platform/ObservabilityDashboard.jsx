import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis } from "recharts";

import { getObservabilityDashboard } from "../../api/operator.js";
import { useSystem } from "../../context/SystemContext";
import {
  ActionButton,
  EmptyState,
  ErrorState,
  formatCompactNumber,
  formatDateTime,
  InlineBadge,
  LoadingState,
  MetricCard,
  PageShell,
  SurfaceGrid,
  SurfacePanel,
  surfacePalette } from "./SurfacePrimitives";import { safeMap } from "../../utils/safe";

function chartLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
}

function ChartTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-2xl border px-4 py-3 shadow-2xl"
      style={{ background: "rgba(10,12,18,0.98)", borderColor: surfacePalette.border }}>

      {label ?
      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: surfacePalette.muted }}>
          {label}
        </div> :
      null}
      <div className="space-y-2 text-sm">
        {safeMap(payload, (item) =>
        <div key={item.dataKey} className="flex items-center justify-between gap-4">
            <span style={{ color: item.color }}>{item.name}</span>
            <span style={{ color: surfacePalette.text }}>
              {formatter ? formatter(item.value, item.name) : item.value}
            </span>
          </div>)
        }
      </div>
    </div>);

}

function toneForHealth(status) {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  return "danger";
}

function buildBootDashboard(system) {
  const summary = system?.system_state || {};
  const flows = system?.flows || [];
  return {
    summary: {
      window_hours: 24,
      avg_latency_ms: 0,
      window_requests: 0,
      window_errors: 0,
      error_rate_pct: 0,
      active_flows: summary.active_flows ?? flows.length,
      loop_events: 0,
      agent_events: summary.active_runs ?? 0,
      system_event_total: 0,
      health_status: "unknown"
    },
    request_metrics: {
      recent: [],
      recent_errors: [],
      error_rate_series: []
    },
    loop_activity: [],
    agent_timeline: safeMap(system?.runs || [], (run) => ({
      id: run.run_id,
      run_id: run.run_id,
      trace_id: run.trace_id,
      event_type: run.status,
      timestamp: run.created_at,
      payload: {
        goal_preview: run.goal
      }
    })),
    system_events: {
      recent: [],
      counts: {}
    },
    system_health: {
      latest: null,
      logs: []
    },
    flows: {
      status_counts: flows.reduce((acc, flow) => {
        const key = flow.status || "unknown";
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }, {}),
      recent: flows
    }
  };
}

export default function ObservabilityDashboard() {
  const { system } = useSystem();
  const [data, setData] = useState(() => buildBootDashboard(system));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const dashboard = await getObservabilityDashboard(24);
      setData(dashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load observability data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    setData((current) => {
      const hasRemoteData = Boolean(current?.request_metrics?.recent?.length);
      return hasRemoteData ? current : buildBootDashboard(system);
    });
  }, [system]);

  const summary = data?.summary || {};
  const requestMetrics = data?.request_metrics || {};
  const health = data?.system_health || {};
  const flows = data?.flows || {};

  const errorRateSeries = useMemo(
    () => safeMap(
      requestMetrics.error_rate_series || [], (entry, index) => ({
        index: index + 1,
        label: chartLabel(entry.label),
        errorRate: Number(entry.error_rate || 0),
        errors: Number(entry.errors || 0),
        requests: Number(entry.requests || 0)
      })),
    [requestMetrics]
  );

  const flowStatusSeries = useMemo(
    () => safeMap(
      Object.entries(flows.status_counts || {}), ([status, count]) => ({
        status,
        count
      })),
    [flows]
  );

  const healthSeries = useMemo(
    () => safeMap(
      (health.logs || []).
      slice().
      reverse(),
      (entry) => ({
        label: chartLabel(entry.timestamp),
        latency: Number(entry.avg_latency_ms || 0),
        status: entry.status
      })),
    [health]
  );

  return (
    <PageShell
      eyebrow="System Telemetry"
      title="Observability Dashboard"
      description="Unified operational state across request traffic, loop orchestration, agent activity, health checks, and durable system events."
      actions={<ActionButton tone="ghost" onClick={loadDashboard}>Refresh Signals</ActionButton>}>

      <SurfaceGrid>
        <div className="lg:col-span-3">
          <MetricCard
            label="Error Rate"
            value={`${Number(summary.error_rate_pct || 0).toFixed(1)}%`}
            hint={`${formatCompactNumber(summary.window_errors || 0)} failures in the last ${summary.window_hours || 24}h`}
            tone={Number(summary.error_rate_pct || 0) > 0 ? "warning" : "success"} />

        </div>
        <div className="lg:col-span-3">
          <MetricCard
            label="Loop Events"
            value={formatCompactNumber(summary.loop_events || 0)}
            hint="Derived from system event stream."
            tone="info" />

        </div>
        <div className="lg:col-span-3">
          <MetricCard
            label="Agent Events"
            value={formatCompactNumber(summary.agent_events || 0)}
            hint="Lifecycle events recorded for agent execution."
            tone="info" />

        </div>
        <div className="lg:col-span-3">
          <MetricCard
            label="System Health"
            value={String(summary.health_status || "unknown")}
            hint={`${Math.round(summary.avg_latency_ms || 0)} ms avg request latency`}
            tone={toneForHealth(summary.health_status)} />

        </div>
      </SurfaceGrid>

      {loading ? <LoadingState label="Loading observability surfaces" /> : null}
      {!loading && error ? <ErrorState message={error} onRetry={loadDashboard} /> : null}

      {!loading && !error ?
      <>
          <SurfaceGrid>
            <div className="lg:col-span-7">
              <SurfacePanel
              title="Error Rate Tracking"
              subtitle="Request-level error rate over the current observability window.">

                {errorRateSeries.length ?
              <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={errorRateSeries}>
                        <defs>
                          <linearGradient id="errorRateFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={surfacePalette.danger} stopOpacity={0.38} />
                            <stop offset="95%" stopColor={surfacePalette.danger} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="label" minTickGap={38} stroke={surfacePalette.muted} />
                        <YAxis stroke={surfacePalette.muted} />
                        <Tooltip content={<ChartTooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />} />
                        <Area
                      type="monotone"
                      dataKey="errorRate"
                      name="Error rate"
                      stroke={surfacePalette.danger}
                      fill="url(#errorRateFill)"
                      strokeWidth={2} />

                      </AreaChart>
                    </ResponsiveContainer>
                  </div> :

              <EmptyState title="No request metrics yet" description="Error tracking appears once authenticated traffic has been recorded." />
              }
              </SurfacePanel>
            </div>

            <div className="lg:col-span-5">
              <SurfacePanel
              title="System Health Metrics"
              subtitle="Latest persisted health checks and average endpoint latency.">

                {healthSeries.length ?
              <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={healthSeries}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="label" minTickGap={32} stroke={surfacePalette.muted} />
                        <YAxis stroke={surfacePalette.muted} />
                        <Tooltip content={<ChartTooltip formatter={(value) => `${Math.round(value)} ms`} />} />
                        <Bar dataKey="latency" name="Avg latency" fill={surfacePalette.info} radius={[8, 8, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div> :

              <EmptyState title="No health logs" description="System health appears once the health logger has persisted checks." />
              }
              </SurfacePanel>
            </div>
          </SurfaceGrid>

          <SurfaceGrid>
            <div className="lg:col-span-5">
              <SurfacePanel
              title="Loop Activity Stream"
              subtitle="Recent orchestration decisions emitted through SystemEvent.">

                {data?.loop_activity?.length ?
              <div className="space-y-3">
                    {safeMap(data.loop_activity.slice(0, 10), (event) =>
                <div
                  key={event.id}
                  className="rounded-[18px] border px-4 py-3"
                  style={{ borderColor: surfacePalette.border }}>

                        <div className="flex flex-wrap items-center gap-2">
                          <InlineBadge tone="info">{event.type}</InlineBadge>
                          {event.trace_id ? <InlineBadge>{event.trace_id}</InlineBadge> : null}
                        </div>
                        <div className="mt-2 text-sm" style={{ color: surfacePalette.text }}>
                          {event.payload?.next_action?.title || event.payload?.next_action || event.payload?.trigger_event || "Loop event recorded"}
                        </div>
                        <div className="mt-1 text-xs" style={{ color: surfacePalette.muted }}>
                          {formatDateTime(event.timestamp)}
                        </div>
                      </div>)
                }
                  </div> :

              <EmptyState title="No loop activity" description="Loop adjustments will appear here after orchestrator activity." />
              }
              </SurfacePanel>
            </div>

            <div className="lg:col-span-7">
              <SurfacePanel
              title="Agent Execution Timeline"
              subtitle="Recent agent lifecycle events with run and trace context.">

                {data?.agent_timeline?.length ?
              <div className="space-y-3">
                    {safeMap(data.agent_timeline.slice(0, 12), (event) =>
                <div
                  key={event.id}
                  className="flex flex-col gap-3 rounded-[18px] border px-4 py-3 md:flex-row md:items-center md:justify-between"
                  style={{ borderColor: surfacePalette.border }}>

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <InlineBadge tone="info">{event.event_type}</InlineBadge>
                            <InlineBadge>{event.run_id}</InlineBadge>
                            {event.trace_id ? <InlineBadge tone="info">{event.trace_id}</InlineBadge> : null}
                          </div>
                          <div className="mt-2 text-sm" style={{ color: surfacePalette.text }}>
                            {event.payload?.goal_preview || event.payload?.error || event.payload?.event_type || "Agent event recorded"}
                          </div>
                        </div>
                        <div className="text-xs" style={{ color: surfacePalette.muted }}>
                          {formatDateTime(event.timestamp)}
                        </div>
                      </div>)
                }
                  </div> :

              <EmptyState title="No agent timeline" description="Agent lifecycle events will populate after runs are created." />
              }
              </SurfacePanel>
            </div>
          </SurfaceGrid>

          <SurfaceGrid>
            <div className="lg:col-span-4">
              <SurfacePanel
              title="Flow State"
              subtitle="Execution distribution across the current flow backlog.">

                {flowStatusSeries.length ?
              <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={flowStatusSeries}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="status" stroke={surfacePalette.muted} />
                        <YAxis allowDecimals={false} stroke={surfacePalette.muted} />
                        <Tooltip content={<ChartTooltip />} />
                        <Bar dataKey="count" name="Runs" fill={surfacePalette.accent} radius={[8, 8, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div> :

              <EmptyState title="No flow runs" description="Flow execution counts will appear after workflow activity." />
              }
              </SurfacePanel>
            </div>

            <div className="lg:col-span-4">
              <SurfacePanel
              title="Recent Error Requests"
              subtitle="Latest request failures with trace IDs.">

                {requestMetrics.recent_errors?.length ?
              <div className="space-y-3">
                    {safeMap(requestMetrics.recent_errors.slice(0, 8), (row) =>
                <div key={`${row.trace_id || row.request_id}-${row.created_at}`} className="rounded-[18px] border px-4 py-3" style={{ borderColor: surfacePalette.border }}>
                        <div className="flex flex-wrap items-center gap-2">
                          <InlineBadge tone="danger">{row.status_code}</InlineBadge>
                          <InlineBadge tone="info">{row.method}</InlineBadge>
                          {row.trace_id ? <InlineBadge>{row.trace_id}</InlineBadge> : null}
                        </div>
                        <div className="mt-2 text-sm" style={{ color: surfacePalette.text }}>{row.path}</div>
                        <div className="mt-1 text-xs" style={{ color: surfacePalette.muted }}>{formatDateTime(row.created_at)}</div>
                      </div>)
                }
                  </div> :

              <EmptyState title="No recent errors" description="5xx request failures will surface here automatically." />
              }
              </SurfacePanel>
            </div>

            <div className="lg:col-span-4">
              <SurfacePanel
              title="System Event Feed"
              subtitle="Cross-domain event ledger used to correlate execution, loop, and memory activity.">

                {data?.system_events?.recent?.length ?
              <div className="space-y-3">
                    {safeMap(data.system_events.recent.slice(0, 8), (event) =>
                <div key={event.id} className="rounded-[18px] border px-4 py-3" style={{ borderColor: surfacePalette.border }}>
                        <div className="flex flex-wrap items-center gap-2">
                          <InlineBadge tone="success">{event.type}</InlineBadge>
                          {event.trace_id ? <InlineBadge>{event.trace_id}</InlineBadge> : null}
                        </div>
                        <div className="mt-1 text-xs" style={{ color: surfacePalette.muted }}>{formatDateTime(event.timestamp)}</div>
                      </div>)
                }
                  </div> :

              <EmptyState title="No system events" description="Durable event records will appear once the runtime emits them." />
              }
              </SurfacePanel>
            </div>
          </SurfaceGrid>
        </> :
      null}
    </PageShell>);

}
