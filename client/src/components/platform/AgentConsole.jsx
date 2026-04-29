import React, { useState, useEffect, useCallback } from "react";
import {
  createAgentRun,
  getAgentRuns,
  getAgentRunSteps,
  approveAgentRun,
  rejectAgentRun,
  getAgentTools,
  getAgentTrust,
  updateAgentTrust,
  getAgentSuggestions,
  fetchRunEvents,
} from "../../api/agent.js";
import { postScoreFeedback } from "../../api/analytics.js";
import { useAuth } from "../../context/AuthContext";
import { useSystem } from "../../context/SystemContext";
import { AdminAccessRequired } from "../shared/AdminApiErrorBoundary";
import { LoadingPanel } from "../shared/LoadingPanel";
import { EmptyState } from "../shared/EmptyState";
import { InlineErrorBoundary } from "../shared/ErrorBoundary";
import { Toast } from "../shared/Toast";
import { useToast } from "../../utils/useToast";

// ── Risk badge ────────────────────────────────────────────────────────────────
import { safeMap } from "../../utils/safe";
const RiskBadge = ({ risk }) => {
  const colors = {
    low: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
    medium: "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
    high: "bg-red-500/10 text-red-400 border border-red-500/20"
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${colors[risk] || colors.high}`}>
      {risk || "?"}
    </span>);

};

// ── Status badge ──────────────────────────────────────────────────────────────

const StatusBadge = ({ status }) => {
  const colors = {
    pending_approval: "bg-yellow-500/10 text-yellow-300 border border-yellow-500/20",
    approved: "bg-blue-500/10 text-blue-300 border border-blue-500/20",
    executing: "bg-[#00ffaa]/10 text-[#00ffaa] border border-[#00ffaa]/20",
    completed: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
    failed: "bg-red-500/10 text-red-400 border border-red-500/20",
    rejected: "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20"
  };
  const labels = {
    pending_approval: "Awaiting Approval",
    approved: "Approved",
    executing: "Executing",
    completed: "Completed",
    failed: "Failed",
    rejected: "Rejected"
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${colors[status] || ""}`}>
      {labels[status] || status}
    </span>);

};

// ── Step row ──────────────────────────────────────────────────────────────────

const StepRow = ({ step, index }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-zinc-800/60 rounded-lg overflow-hidden mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/30 transition-colors">

        <span className="text-xs font-mono text-zinc-500 w-5">{index + 1}</span>
        <span className="font-mono text-xs text-[#00ffaa] w-36 truncate">{step.tool_name}</span>
        <RiskBadge risk={step.risk_level} />
        <span className="flex-1 text-xs text-zinc-300 truncate">{step.description}</span>
        {step.status && <StatusBadge status={step.status} />}
        {step.execution_ms &&
        <span className="text-[10px] text-zinc-500">{step.execution_ms}ms</span>
        }
        <span className="text-zinc-500 text-[10px]">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded &&
      <div className="px-4 pb-3 border-t border-zinc-800/60 bg-zinc-950/50">
          {step.result &&
        <pre className="text-[10px] text-zinc-300 mt-2 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(step.result, null, 2)}
            </pre>
        }
          {step.error_message &&
        <p className="text-xs text-red-400 mt-2">{step.error_message}</p>
        }
        </div>
      }
    </div>);

};

// ── Run card ──────────────────────────────────────────────────────────────────

const RunCard = ({ run, onApprove, onReject, onSelect, isSelected }) => {
  const isPending = run.status === "pending_approval";
  const steps = run.plan?.steps || [];

  return (
    <div
      className={`border rounded-xl p-4 cursor-pointer transition-all ${
      isSelected ?
      "border-[#00ffaa]/40 bg-[#00ffaa]/5" :
      "border-zinc-800/60 hover:border-zinc-700/60 bg-zinc-950/30"}`
      }
      onClick={() => onSelect(run)}>

      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-sm font-medium text-zinc-100 leading-snug flex-1 line-clamp-2">
          {run.goal}
        </p>
        <div className="flex items-center gap-2 flex-shrink-0">
          <RiskBadge risk={run.overall_risk} />
          <StatusBadge status={run.status} />
        </div>
      </div>

      {run.executive_summary &&
      <p className="text-xs text-zinc-400 mb-3 line-clamp-2">{run.executive_summary}</p>
      }

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-[10px] text-zinc-500">
          <span>{steps.length} step{steps.length !== 1 ? "s" : ""}</span>
          {run.steps_completed > 0 &&
          <span>{run.steps_completed}/{run.steps_total} done</span>
          }
          <span>{run.created_at ? new Date(run.created_at).toLocaleString() : ""}</span>
        </div>

        {isPending &&
        <div className="flex gap-2">
            <button
            onClick={(e) => {e.stopPropagation();onApprove(run.run_id);}}
            className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded bg-[#00ffaa] text-black hover:bg-[#00ffaa]/80 transition-colors">

              Approve
            </button>
            <button
            onClick={(e) => {e.stopPropagation();onReject(run.run_id);}}
            className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded border border-zinc-700 text-zinc-400 hover:bg-zinc-800 transition-colors">

              Reject
            </button>
          </div>
        }
      </div>
    </div>);

};

// ── Plan preview panel ────────────────────────────────────────────────────────

const RunOutcomeFeedback = ({ runId }) => {
  const [feedbackValue, setFeedbackValue] = useState(null);
  const [saving, setSaving] = useState(false);

  const submitFeedback = async (value) => {
    setSaving(true);
    try {
      await postScoreFeedback({
        source_type: "agent",
        source_id: runId,
        feedback_value: value
      });
      setFeedbackValue(value);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-4 flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-wider text-zinc-500">Run Outcome</span>
      <button
        onClick={() => submitFeedback(1)}
        disabled={saving}
        className={`px-3 py-1 rounded-full border text-[10px] font-bold uppercase tracking-wider transition-colors ${
        feedbackValue === 1 ?
        "border-emerald-500 bg-emerald-500/20 text-emerald-300" :
        "border-zinc-700 text-zinc-400 hover:bg-zinc-800"}`
        }>

        Helpful
      </button>
      <button
        onClick={() => submitFeedback(-1)}
        disabled={saving}
        className={`px-3 py-1 rounded-full border text-[10px] font-bold uppercase tracking-wider transition-colors ${
        feedbackValue === -1 ?
        "border-red-500 bg-red-500/20 text-red-300" :
        "border-zinc-700 text-zinc-400 hover:bg-zinc-800"}`
        }>

        Not Helpful
      </button>
    </div>);

};

const PlanPreview = ({ run, steps, loading }) => {
  if (!run) return null;
  const planSteps = run.plan?.steps || [];

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <div className="flex items-center gap-3 mb-2">
          <h3 className="text-sm font-bold text-zinc-100">Execution Plan</h3>
          <RiskBadge risk={run.overall_risk} />
          <StatusBadge status={run.status} />
        </div>
        <p className="text-xs text-zinc-400">{run.goal}</p>
      </div>

      {run.executive_summary &&
      <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-lg p-3 mb-4">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Executive Summary</p>
          <p className="text-sm text-zinc-200">{run.executive_summary}</p>
        </div>
      }

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {loading ?
        <p className="text-xs text-zinc-500">Loading steps...</p> :
        steps.length > 0 ?
        <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Steps</p>
            {safeMap(steps, (step, i) =>
          <StepRow key={i} step={step} index={i} />)
          }
          </div> :
        planSteps.length > 0 ?
        <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Planned Steps</p>
            {safeMap(planSteps, (step, i) =>
          <div key={i} className="flex items-start gap-3 px-4 py-3 border border-zinc-800/60 rounded-lg mb-2">
                <span className="text-xs font-mono text-zinc-500 w-5 pt-0.5">{i + 1}</span>
                <span className="font-mono text-xs text-[#00ffaa] w-36 flex-shrink-0">{step.tool}</span>
                <RiskBadge risk={step.risk_level} />
                <span className="flex-1 text-xs text-zinc-300">{step.description}</span>
              </div>)
          }
          </div> :
        null}

        {run.result &&
        <div className="mt-4">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Result</p>
            <pre className="text-[10px] text-zinc-300 bg-zinc-900/50 border border-zinc-800/60 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(run.result, null, 2)}
            </pre>
          </div>
        }

        {(run.status === "completed" || run.status === "failed") &&
        <RunOutcomeFeedback runId={run.run_id} />
        }
      </div>
    </div>);

};

// ── Trust settings panel ──────────────────────────────────────────────────────

const TrustPanel = ({ trust, onUpdate, tools }) => {
  const [low, setLow] = useState(trust?.auto_execute_low || false);
  const [medium, setMedium] = useState(trust?.auto_execute_medium || false);
  const [allowedTools, setAllowedTools] = useState(trust?.allowed_auto_grant_tools || []);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLow(trust?.auto_execute_low || false);
    setMedium(trust?.auto_execute_medium || false);
    setAllowedTools(trust?.allowed_auto_grant_tools || []);
  }, [trust]);

  const autoGrantableTools = (tools || []).
  filter((tool) => tool.risk === "low" || tool.risk === "medium").
  sort((a, b) => a.name.localeCompare(b.name));

  const lockedTools = (tools || []).
  filter((tool) => tool.name === "genesis.message");

  const toggleTool = (toolName) => {
    setAllowedTools((current) =>
    current.includes(toolName) ?
    current.filter((name) => name !== toolName) :
    [...current, toolName].sort()
    );
  };

  const save = async () => {
    setSaving(true);
    try {
      await onUpdate({
        auto_execute_low: low,
        auto_execute_medium: medium,
        allowed_auto_grant_tools: allowedTools
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-4">
      <h4 className="text-xs font-bold text-zinc-300 uppercase tracking-wider mb-3">Trust Settings</h4>
      <p className="text-[10px] text-zinc-500 mb-4">
        High-risk plans always require approval regardless of these settings.
      </p>
      <div className="space-y-3">
        <label className="flex items-center justify-between">
          <span className="text-xs text-zinc-300">Auto-execute low-risk plans</span>
          <input
            type="checkbox"
            checked={low}
            onChange={(e) => setLow(e.target.checked)}
            className="accent-[#00ffaa]" />

        </label>
        <label className="flex items-center justify-between">
          <span className="text-xs text-zinc-300">Auto-execute medium-risk plans</span>
          <input
            type="checkbox"
            checked={medium}
            onChange={(e) => setMedium(e.target.checked)}
            className="accent-yellow-400" />

        </label>
      </div>
      <div className="mt-5">
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">
          Tool-Level Auto-Grant Policy
        </p>
        <div className="space-y-2">
          {safeMap(autoGrantableTools, (tool) =>
          <label
            key={tool.name}
            className="flex items-center justify-between gap-3 border border-zinc-800/60 rounded-lg px-3 py-2">

              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-200 font-mono">{tool.name}</span>
                  <RiskBadge risk={tool.risk} />
                </div>
                <p className="text-[10px] text-zinc-500 mt-1">{tool.description}</p>
              </div>
              <input
              type="checkbox"
              checked={allowedTools.includes(tool.name)}
              onChange={() => toggleTool(tool.name)}
              className="accent-[#00ffaa]" />

            </label>)
          }
          {safeMap(lockedTools, (tool) =>
          <label
            key={tool.name}
            className="flex items-center justify-between gap-3 border border-red-500/20 rounded-lg px-3 py-2 opacity-80">

              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-200 font-mono">{tool.name}</span>
                  <RiskBadge risk={tool.risk} />
                </div>
                <p className="text-[10px] text-zinc-500 mt-1">
                  Locked. High-risk tools cannot be auto-granted.
                </p>
              </div>
              <input
              type="checkbox"
              checked={false}
              disabled
              className="accent-red-500" />

            </label>)
          }
        </div>
      </div>
      <button
        onClick={save}
        disabled={saving}
        className="mt-4 w-full py-2 text-[10px] font-bold uppercase tracking-wider rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors disabled:opacity-50">

        {saving ? "Saving..." : "Save Settings"}
      </button>
    </div>);

};

// ── Suggestion chips ─────────────────────────────────────────────────────────

const TOOL_CHIP_COLORS = {
  "memory.recall": "border-blue-500/30 text-blue-300 hover:bg-blue-500/10",
  "task.create": "border-[#00ffaa]/30 text-[#00ffaa] hover:bg-[#00ffaa]/10",
  "arm.analyze": "border-purple-500/30 text-purple-300 hover:bg-purple-500/10",
  "genesis.message": "border-yellow-500/30 text-yellow-300 hover:bg-yellow-500/10"
};

const SuggestionChips = ({ suggestions, onSelect }) => {
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div className="mb-4">
      <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2">Suggested Actions</p>
      <div className="flex flex-wrap gap-2">
        {safeMap(suggestions, (s, i) =>
        <button
          key={i}
          title={s.reason}
          onClick={() => onSelect(s.suggested_goal)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-medium transition-colors ${
          TOOL_CHIP_COLORS[s.tool] || "border-zinc-700 text-zinc-400 hover:bg-zinc-800"}`
          }>

            <span className="font-mono text-[10px] opacity-70">{s.tool}</span>
            <span className="truncate max-w-[180px]">{s.suggested_goal}</span>
          </button>)
        }
      </div>
    </div>);

};

// ── Event type color helper ───────────────────────────────────────────────────

function eventTypeColor(eventType) {
  const colors = {
    PLAN_CREATED: "#6366f1",
    APPROVED: "#10b981",
    REJECTED: "#ef4444",
    EXECUTION_STARTED: "#3b82f6",
    COMPLETED: "#059669",
    EXECUTION_FAILED: "#dc2626",
    CAPABILITY_DENIED: "#ea580c",
    RECOVERED: "#f59e0b",
    REPLAY_CREATED: "#8b5cf6",
    STEP_EXECUTED: "#64748b",
    STEP_FAILED: "#b91c1c"
  };
  return colors[eventType] || "#6b7280";
}

// ── Main AgentConsole ─────────────────────────────────────────────────────────

export default function AgentConsole() {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <AdminAccessRequired />;
  const { system } = useSystem();
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [runs, setRuns] = useState(system?.runs || []);
  const [selectedRun, setSelectedRun] = useState(null);
  const [selectedSteps, setSelectedSteps] = useState([]);
  const [stepsLoading, setStepsLoading] = useState(false);
  const [tools, setTools] = useState([]);
  const [trust, setTrust] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [activeTab, setActiveTab] = useState("runs"); // runs | tools | trust
  const [error, setError] = useState(null);
  const [runEvents, setRunEvents] = useState([]);
  const [activeDetailTab, setActiveDetailTab] = useState("steps"); // "steps" | "timeline"
  const [runsLoading, setRunsLoading] = useState(true);
  const { toast, showToast, clearToast } = useToast();

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const data = await getAgentRuns();
      setRuns(data || []);
    } catch (e) {
      console.error("Failed to load runs", e);
      showToast(e?.message || "Failed to load agent runs.");
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const loadTools = useCallback(async () => {
    try {
      const data = await getAgentTools();
      setTools(data || []);
    } catch (e) {
      console.error("Failed to load tools", e);
      showToast(e?.message || "Failed to load agent tools.");
    }
  }, []);

  const loadTrust = useCallback(async () => {
    try {
      const data = await getAgentTrust();
      setTrust(data);
    } catch (e) {
      console.error("Failed to load trust", e);
      showToast(e?.message || "Failed to load trust settings.");
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    try {
      const data = await getAgentSuggestions();
      setSuggestions(data || []);
    } catch (e) {

      // Suggestions are non-critical — fail silently
    }}, []);

  useEffect(() => {
    loadRuns();
    loadTools();
    loadTrust();
    loadSuggestions();
  }, [loadRuns, loadTools, loadTrust, loadSuggestions]);

  useEffect(() => {
    if ((system?.runs || []).length > 0) {
      setRuns(system.runs);
    }
  }, [system]);

  const handleSelect = async (run) => {
    setSelectedRun(run);
    setSelectedSteps([]);
    setRunEvents([]);
    setActiveDetailTab("steps");
    if (run.status === "completed" || run.status === "failed") {
      setStepsLoading(true);
      try {
        const steps = await getAgentRunSteps(run.run_id);
        setSelectedSteps(steps || []);
      } catch (e) {
        console.error("Failed to load steps", e);
        showToast(e?.message || "Failed to load run steps.");
      } finally {
        setStepsLoading(false);
      }
    }
    fetchRunEvents(run.run_id).
    then((data) => setRunEvents(data?.events || [])).
    catch(() => setRunEvents([]));
  };

  const handleSubmit = async () => {
    if (!goal.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const run = await createAgentRun({ goal: goal.trim() });
      setGoal("");
      await loadRuns();
      setSelectedRun(run);
    } catch (e) {
      setError(e.message || "Failed to create agent run");
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = async (runId) => {
    try {
      const updated = await approveAgentRun(runId);
      await loadRuns();
      if (selectedRun?.run_id === runId) {
        setSelectedRun(updated);
        if (updated.status === "completed" || updated.status === "failed") {
          const steps = await getAgentRunSteps(runId);
          setSelectedSteps(steps || []);
        }
      }
    } catch (e) {
      setError(e.message || "Failed to approve run");
    }
  };

  const handleReject = async (runId) => {
    try {
      const updated = await rejectAgentRun(runId);
      await loadRuns();
      if (selectedRun?.run_id === runId) {
        setSelectedRun(updated);
      }
    } catch (e) {
      setError(e.message || "Failed to reject run");
    }
  };

  const handleTrustUpdate = async (updates) => {
    const updated = await updateAgentTrust(updates);
    setTrust(updated);
  };

  const pendingRuns = runs.filter((r) => r.status === "pending_approval");

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-black text-zinc-100 tracking-tight">Agent Console</h2>
        <p className="text-xs text-zinc-500 mt-1">
          Type a goal. A.I.N.D.Y. generates a plan and executes it with your approval.
        </p>
      </div>

      {/* Suggestion chips */}
      <SuggestionChips
        suggestions={suggestions}
        onSelect={(suggestedGoal) => setGoal(suggestedGoal)} />


      {/* Goal input */}
      <div className="mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !submitting && handleSubmit()}
            placeholder="e.g. Find leads in the AI consulting space and create a follow-up task"
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-[#00ffaa]/50 transition-colors" />

          <button
            onClick={handleSubmit}
            disabled={submitting || !goal.trim()}
            className="px-6 py-3 bg-[#00ffaa] text-black font-bold text-sm rounded-xl hover:bg-[#00ffaa]/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0">

            {submitting ? "Planning..." : "Run Agent"}
          </button>
        </div>
        {error &&
        <p className="text-xs text-red-400 mt-2">{error}</p>
        }
      </div>

      {/* Pending approval banner */}
      {pendingRuns.length > 0 &&
      <div className="mb-4 bg-yellow-500/5 border border-yellow-500/20 rounded-xl px-4 py-3">
          <p className="text-xs text-yellow-300 font-medium">
            {pendingRuns.length} plan{pendingRuns.length > 1 ? "s" : ""} awaiting your approval
          </p>
        </div>
      }

      {/* Main content */}
      <div className="flex gap-6 flex-1 min-h-0">
        {/* Left: tabs + list */}
        <div className="w-80 flex flex-col flex-shrink-0">
          {/* Tabs */}
          <div className="flex gap-1 mb-4 bg-zinc-900/50 rounded-lg p-1">
            {safeMap(["runs", "tools", "trust"], (tab) =>
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded transition-colors ${
              activeTab === tab ?
              "bg-zinc-800 text-zinc-100" :
              "text-zinc-500 hover:text-zinc-300"}`
              }>

                {tab === "runs" ?
              <span>
                    {`Runs${runs.length ? ` (${runs.length})` : ""}`}
                    {pendingRuns.length > 0 &&
                <span style={{
                  background: "#f59e0b",
                  color: "#fff",
                  borderRadius: "10px",
                  padding: "1px 6px",
                  fontSize: "10px",
                  marginLeft: "5px",
                  fontWeight: 700
                }}>
                        {pendingRuns.length}
                      </span>
                }
                  </span> :
              tab === "tools" ? "Tools" : "Trust"}
              </button>)
            }
          </div>

          {/* Run list */}
          {activeTab === "runs" &&
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
              {runsLoading ? <LoadingPanel label="Loading agent runs..." /> :
            runs.length === 0 ?
            <EmptyState
              message="No agent runs yet."
              hint="Submit an objective above to start an agent run." /> : safeMap(

              runs, (run) =>
              <RunCard
                key={run.run_id}
                run={run}
                onApprove={handleApprove}
                onReject={handleReject}
                onSelect={handleSelect}
                isSelected={selectedRun?.run_id === run.run_id} />)


            }
            </div>
          }

          {/* Tool list */}
          {activeTab === "tools" &&
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
              {safeMap(tools, (tool) =>
            <div key={tool.name} className="border border-zinc-800/60 rounded-lg px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs text-[#00ffaa]">{tool.name}</span>
                    <RiskBadge risk={tool.risk} />
                  </div>
                  <p className="text-[10px] text-zinc-500">{tool.description}</p>
                </div>)
            }
            </div>
          }

          {/* Trust settings */}
          {activeTab === "trust" &&
          <TrustPanel trust={trust} onUpdate={handleTrustUpdate} tools={tools} />
          }
        </div>

        {/* Right: plan detail */}
        <div className="flex-1 min-w-0 border border-zinc-800/60 rounded-xl p-5 overflow-y-auto custom-scrollbar">
          {selectedRun ?
          <div className="flex flex-col h-full">
              {/* Detail tab switcher */}
              <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
                <button
                onClick={() => setActiveDetailTab("steps")}
                style={{
                  padding: "4px 12px",
                  borderRadius: "4px",
                  border: "1px solid #3f3f46",
                  background: activeDetailTab === "steps" ? "#3b82f6" : "transparent",
                  color: activeDetailTab === "steps" ? "#fff" : "#a1a1aa",
                  cursor: "pointer",
                  fontSize: "12px",
                  fontWeight: 600
                }}>

                  Steps
                </button>
                <button
                onClick={() => setActiveDetailTab("timeline")}
                style={{
                  padding: "4px 12px",
                  borderRadius: "4px",
                  border: "1px solid #3f3f46",
                  background: activeDetailTab === "timeline" ? "#3b82f6" : "transparent",
                  color: activeDetailTab === "timeline" ? "#fff" : "#a1a1aa",
                  cursor: "pointer",
                  fontSize: "12px",
                  fontWeight: 600
                }}>

                  Timeline {runEvents.length > 0 && `(${runEvents.length})`}
                </button>
              </div>

              {activeDetailTab === "steps" &&
            <InlineErrorBoundary name="Agent Steps">
            <PlanPreview
              run={selectedRun}
              steps={selectedSteps}
              loading={stepsLoading} />
                </InlineErrorBoundary>

            }

              {activeDetailTab === "timeline" &&
            <InlineErrorBoundary name="Agent Timeline">
            <div>
                  {runEvents.length === 0 ?
              <p style={{ color: "#6b7280", fontStyle: "italic", fontSize: "12px" }}>
                      No events recorded (run may predate N+8).
                    </p> :

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      {safeMap(runEvents, (evt, i) =>
                <div
                  key={evt.id || i}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "6px",
                    border: "1px solid #27272a",
                    background: "#09090b"
                  }}>

                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{
                      background: eventTypeColor(evt.event_type),
                      color: "#fff",
                      borderRadius: "4px",
                      padding: "2px 8px",
                      fontSize: "11px",
                      fontWeight: 600,
                      letterSpacing: "0.05em"
                    }}>
                              {evt.event_type}
                            </span>
                            <span style={{ color: "#6b7280", fontSize: "12px" }}>
                              {evt.occurred_at ? new Date(evt.occurred_at).toLocaleTimeString() : ""}
                            </span>
                          </div>
                          {evt.payload && Object.keys(evt.payload).length > 0 &&
                  <div style={{ marginTop: "4px", fontSize: "12px", color: "#a1a1aa" }}>
                              {evt.event_type === "STEP_EXECUTED" || evt.event_type === "STEP_FAILED" ?
                    <span>
                                  Step {evt.payload.step_index} · {evt.payload.tool_name}
                                  {evt.payload.execution_ms ? ` · ${evt.payload.execution_ms}ms` : ""}
                                  {evt.payload.error_message ? ` · ${evt.payload.error_message}` : ""}
                                </span> :

                    <span>
                                  {safeMap(
                      Object.entries(evt.payload).filter(([, v]) => v !== null && v !== undefined && v !== ""),
                      ([k, v]) => `${k}: ${v}`
                    ).join(" · ")}
                                </span>
                    }
                            </div>
                  }
                        </div>)
                }
                    </div>
              }
                </div>
                </InlineErrorBoundary>
            }
            </div> :

          <div className="flex items-center justify-center h-full">
              <p className="text-xs text-zinc-600">Select a run to view its plan</p>
            </div>
          }
        </div>
      </div>
      <Toast toast={toast} onDismiss={clearToast} />
    </div>);

}
