import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { approveAgentRun, getAgentRuns, rejectAgentRun } from "../../api/agent.js";
import { useAuth } from "../../context/AuthContext";
import { AdminAccessRequired } from "../shared/AdminApiErrorBoundary";
import {
  ActionButton,
  EmptyState,
  ErrorState,
  formatDateTime,
  formatRelativeTime,
  InlineBadge,
  LoadingState,
  PageShell,
  SurfaceGrid,
  SurfacePanel,
  MetricCard,
  statusTone,
  surfacePalette } from "./SurfacePrimitives";import { safeMap } from "../../utils/safe";

const APPROVAL_EVENT = "agent-approval-count-changed";

function emitApprovalCountChanged() {
  window.dispatchEvent(new Event(APPROVAL_EVENT));
}

function summarizePlan(run) {
  const steps = run?.plan?.steps || [];
  if (!steps.length) return "No plan steps were provided.";
  return safeMap(steps.
  slice(0, 3),
  (step) => step.description || step.tool || "Unnamed step").
  join(" • ");
}

function ApprovalRow({ run, pendingAction, onApprove, onReject }) {
  const steps = run?.plan?.steps || [];
  const capabilities = run?.allowed_capabilities || [];
  const grantedTools = run?.granted_tools || [];

  return (
    <article
      className="rounded-[22px] border p-5"
      style={{
        background: "rgba(255,255,255,0.02)",
        borderColor: "rgba(255,255,255,0.08)"
      }}>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <InlineBadge tone={statusTone(run.status)}>{run.status.replaceAll("_", " ")}</InlineBadge>
            <InlineBadge tone={statusTone(run.overall_risk)}>{run.overall_risk} risk</InlineBadge>
            <InlineBadge tone="info">{steps.length} steps</InlineBadge>
            {run.agent_type ? <InlineBadge>{run.agent_type}</InlineBadge> : null}
          </div>
          <h3 className="mt-4 text-xl font-semibold tracking-[-0.03em]" style={{ color: surfacePalette.text }}>
            {run.goal}
          </h3>
          <p className="mt-2 text-sm leading-7" style={{ color: surfacePalette.muted }}>
            {run.executive_summary || summarizePlan(run)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton
            onClick={() => onApprove(run.run_id)}
            disabled={pendingAction === run.run_id}>

            {pendingAction === run.run_id ? "Applying" : "Approve"}
          </ActionButton>
          <ActionButton
            tone="danger"
            onClick={() => onReject(run.run_id)}
            disabled={pendingAction === run.run_id}>

            Reject
          </ActionButton>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]">
        <div className="rounded-[18px] border p-4" style={{ borderColor: surfacePalette.border }}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
            Planned Steps
          </div>
          <div className="mt-3 space-y-3">
            {safeMap(steps, (step, index) =>
            <div key={`${run.run_id}-${index}`} className="rounded-2xl border p-3" style={{ borderColor: surfacePalette.border }}>
                <div className="flex flex-wrap items-center gap-2">
                  <InlineBadge tone="info">Step {index + 1}</InlineBadge>
                  <InlineBadge>{step.tool}</InlineBadge>
                  <InlineBadge tone={statusTone(step.risk_level)}>{step.risk_level}</InlineBadge>
                </div>
                <div className="mt-3 text-sm font-medium" style={{ color: surfacePalette.text }}>
                  {step.description || "No description provided."}
                </div>
                {step.args ?
              <pre
                className="mt-3 overflow-x-auto rounded-2xl p-3 text-xs"
                style={{
                  background: "rgba(4, 17, 13, 0.9)",
                  color: "#8fffd0"
                }}>

                    {JSON.stringify(step.args, null, 2)}
                  </pre> :
              null}
              </div>)
            }
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[18px] border p-4" style={{ borderColor: surfacePalette.border }}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
              Review Metadata
            </div>
            <dl className="mt-4 grid grid-cols-1 gap-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <dt style={{ color: surfacePalette.muted }}>Created</dt>
                <dd style={{ color: surfacePalette.text }}>{formatDateTime(run.created_at)}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt style={{ color: surfacePalette.muted }}>Age</dt>
                <dd style={{ color: surfacePalette.text }}>{formatRelativeTime(run.created_at)}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt style={{ color: surfacePalette.muted }}>Run ID</dt>
                <dd className="truncate font-mono text-xs" style={{ color: surfacePalette.text }}>
                  {run.run_id}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-[18px] border p-4" style={{ borderColor: surfacePalette.border }}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
              Granted Capabilities
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {capabilities.length ? safeMap(capabilities, (capability) =>
              <InlineBadge key={capability} tone="success">
                  {capability}
                </InlineBadge>) :
              <span className="text-sm" style={{ color: surfacePalette.muted }}>No capabilities embedded yet.</span>}
            </div>
          </div>

          <div className="rounded-[18px] border p-4" style={{ borderColor: surfacePalette.border }}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
              Tool Access
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {grantedTools.length ? safeMap(grantedTools, (tool) =>
              <InlineBadge key={tool}>{tool}</InlineBadge>) :
              <span className="text-sm" style={{ color: surfacePalette.muted }}>No tools auto-granted.</span>}
            </div>
          </div>
        </div>
      </div>
    </article>);

}

export default function AgentApprovalInbox() {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <AdminAccessRequired />;
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState("");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getAgentRuns("pending_approval", 50);
      setRuns(Array.isArray(response) ? response : []);
      emitApprovalCountChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleDecision = useCallback(async (runId, action) => {
    setPendingAction(runId);
    setError("");
    try {
      if (action === "approve") {
        await approveAgentRun(runId);
      } else {
        await rejectAgentRun(runId);
      }
      setRuns((current) => current.filter((run) => run.run_id !== runId));
      emitApprovalCountChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} run.`);
    } finally {
      setPendingAction("");
    }
  }, []);

  const stats = useMemo(() => {
    const highRisk = runs.filter((run) => run.overall_risk === "high").length;
    const capabilities = runs.reduce(
      (count, run) => count + (run.allowed_capabilities?.length || 0),
      0
    );
    return {
      total: runs.length,
      highRisk,
      queuedCapabilities: capabilities
    };
  }, [runs]);

  return (
    <PageShell
      eyebrow="Agent Governance"
      title="Approval Inbox"
      description="Review every queued agent run before execution. Risk, capability scope, and planned steps are visible inline so approval stays operational instead of ceremonial."
      actions={
      <>
          <ActionButton tone="ghost" onClick={loadRuns}>Refresh Queue</ActionButton>
          <Link
          to="/agent"
          className="rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em]"
          style={{ borderColor: surfacePalette.border, color: surfacePalette.text }}>

            Open Agent Console
          </Link>
        </>
      }>

      <SurfaceGrid>
        <div className="lg:col-span-4">
          <MetricCard label="Pending Reviews" value={stats.total} hint="Runs waiting for a human decision." tone="warning" />
        </div>
        <div className="lg:col-span-4">
          <MetricCard label="High-Risk Plans" value={stats.highRisk} hint="These runs include high-risk operations." tone={stats.highRisk ? "danger" : "neutral"} />
        </div>
        <div className="lg:col-span-4">
          <MetricCard label="Queued Capabilities" value={stats.queuedCapabilities} hint="Capability grants embedded across the queue." tone="info" />
        </div>
      </SurfaceGrid>

      <SurfacePanel
        title="Pending Agent Runs"
        subtitle="Approval is required before these runs can execute. Approve to start execution immediately or reject to discard the plan.">

        {loading ? <LoadingState label="Loading pending approvals" /> : null}
        {!loading && error ? <ErrorState message={error} onRetry={loadRuns} /> : null}
        {!loading && !error && runs.length === 0 ?
        <EmptyState
          title="Approval queue is clear"
          description="No runs are currently waiting for review. New high-risk or gated plans will land here automatically." /> :

        null}
        {!loading && !error ?
        <div className="space-y-4">
            {safeMap(runs, (run) =>
          <ApprovalRow
            key={run.run_id}
            run={run}
            pendingAction={pendingAction}
            onApprove={(runId) => handleDecision(runId, "approve")}
            onReject={(runId) => handleDecision(runId, "reject")} />)

          }
          </div> :
        null}
      </SurfacePanel>
    </PageShell>);

}

export { APPROVAL_EVENT, emitApprovalCountChanged };
