// src/components/FlowEngineConsole.jsx
import React, { useState, useCallback, useEffect } from "react";
import {
  buildApiUrl,
  getFlowRuns,
  getFlowRunHistory,
  resumeFlowRun,
  getFlowRegistry,
  getAutomationLogs,
  replayAutomationLog,
  getSchedulerStatus } from
"../api";

// ── Design tokens (A.I.N.D.Y. dark theme) ────────────────────────────────────
import { safeMap } from "../utils/safe";const C = {
  bg0: "#0d1117",
  bg1: "#161b22",
  bg2: "#1a1a1a",
  border0: "#21262d",
  border1: "#30363d",
  text0: "#c9d1d9",
  text1: "#8b949e",
  accent: "#6cf"
};

// ── Status colors (consistent across all panels) ──────────────────────────────
const STATUS_COLOR = {
  running: "#3B82F6",
  waiting: "#F59E0B",
  success: "#10B981",
  failed: "#EF4444",
  retrying: "#F97316",
  pending: "#6B7280"
};

const STATUS_DOT_STYLE = (status) => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  background: STATUS_COLOR[status] || "#6B7280",
  display: "inline-block",
  flexShrink: 0
});

// ── Shared UI helpers ─────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const color = STATUS_COLOR[status] || "#6B7280";
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: "bold",
        color,
        border: `1px solid ${color}`,
        padding: "1px 5px",
        borderRadius: 3,
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}>

      {status}
    </span>);

}

function Badge({ label, color = C.text1 }) {
  return (
    <span
      style={{
        fontSize: 10,
        color,
        background: C.bg0,
        border: `1px solid ${C.border0}`,
        padding: "1px 6px",
        borderRadius: 3,
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}>

      {label}
    </span>);

}

function PanelHeader({ title, lastRefreshed, onRefresh, children }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 16,
        flexWrap: "wrap",
        gap: 8
      }}>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h3 style={{ margin: 0, color: C.text0, fontSize: 15 }}>{title}</h3>
        {children}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {lastRefreshed &&
        <span style={{ fontSize: 11, color: C.text1 }}>
            Refreshed {relativeTime(lastRefreshed)}
          </span>
        }
        <button onClick={onRefresh} style={btnStyle("secondary")}>
          🔄 Refresh
        </button>
      </div>
    </div>);

}

function SummaryBar({ counts, onFilter, activeFilter }) {
  const items = Object.entries(counts).filter(([, n]) => n >= 0);
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
      {safeMap(items, ([status, n]) =>
      <button
        key={status}
        onClick={() => onFilter(activeFilter === status ? null : status)}
        style={{
          padding: "4px 10px",
          borderRadius: 12,
          border: `1px solid ${STATUS_COLOR[status] || C.border0}`,
          background:
          activeFilter === status ?
          STATUS_COLOR[status] + "33" :
          C.bg1,
          color: STATUS_COLOR[status] || C.text1,
          fontSize: 12,
          cursor: "pointer",
          fontWeight: activeFilter === status ? "bold" : "normal"
        }}>

          <span style={STATUS_DOT_STYLE(status)} /> {status}: {n}
        </button>)
      }
    </div>);

}

function LoadingState({ label = "Loading..." }) {
  return (
    <div style={{ padding: "32px 0", textAlign: "center", color: C.text1 }}>
      {label}
    </div>);

}

function ErrorState({ error, onRetry }) {
  return (
    <div
      style={{
        padding: 12,
        background: "#441111",
        border: `1px solid ${STATUS_COLOR.failed}`,
        borderRadius: 6,
        color: "#ff8888",
        marginBottom: 12
      }}>

      <strong>Error:</strong> {error}
      {onRetry &&
      <button onClick={onRetry} style={{ ...btnStyle("secondary"), marginLeft: 12 }}>
          Retry
        </button>
      }
    </div>);

}

function EmptyState({ message, sub }) {
  return (
    <div
      style={{
        padding: "32px 20px",
        textAlign: "center",
        color: C.text1,
        background: C.bg1,
        borderRadius: 8,
        border: `1px solid ${C.border0}`
      }}>

      <div style={{ fontSize: 14, color: C.text0, marginBottom: 8 }}>{message}</div>
      {sub && <div style={{ fontSize: 12 }}>{sub}</div>}
    </div>);

}

function CollapsibleJSON({ label, data }) {
  const [open, setOpen] = useState(false);
  if (!data) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "none",
          border: "none",
          color: C.accent,
          cursor: "pointer",
          fontSize: 12,
          padding: 0,
          marginBottom: 4
        }}>

        {open ? "▼" : "▶"} {label}
      </button>
      {open &&
      <pre
        style={{
          background: C.bg0,
          border: `1px solid ${C.border0}`,
          borderRadius: 4,
          padding: "8px 10px",
          fontSize: 11,
          color: "#9f6",
          overflowX: "auto",
          margin: 0,
          maxHeight: 200,
          overflowY: "auto"
        }}>

          {JSON.stringify(data, null, 2)}
        </pre>
      }
    </div>);

}

// ── Utility ───────────────────────────────────────────────────────────────────

function relativeTime(date) {
  if (!date) return "never";
  const diff = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(date).toLocaleDateString();
}

function duration(start, end) {
  if (!start) return "—";
  const ms = (end ? new Date(end) : new Date()) - new Date(start);
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor(ms % 60000 / 1000)}s`;
}

function truncate(str, n = 80) {
  if (!str) return "";
  return str.length > n ? str.slice(0, n) + "…" : str;
}

function btnStyle(variant = "primary") {
  if (variant === "primary")
  return {
    padding: "6px 14px",
    background: "#007bff",
    color: "#fff",
    border: "none",
    borderRadius: 5,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: "bold"
  };
  if (variant === "danger")
  return {
    padding: "6px 14px",
    background: STATUS_COLOR.failed + "22",
    color: STATUS_COLOR.failed,
    border: `1px solid ${STATUS_COLOR.failed}`,
    borderRadius: 5,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: "bold"
  };
  return {
    padding: "5px 10px",
    background: C.bg1,
    color: C.text0,
    border: `1px solid ${C.border1}`,
    borderRadius: 5,
    cursor: "pointer",
    fontSize: 12
  };
}

function selectStyle() {
  return {
    padding: "5px 8px",
    background: C.bg2,
    color: C.text0,
    border: `1px solid ${C.border1}`,
    borderRadius: 5,
    fontSize: 12,
    cursor: "pointer"
  };
}

// ── Confirmation modal ────────────────────────────────────────────────────────

function ConfirmModal({ message, onConfirm, onCancel }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center"
      }}>

      <div
        style={{
          background: C.bg1,
          border: `1px solid ${C.border1}`,
          borderRadius: 10,
          padding: "24px 28px",
          maxWidth: 420,
          width: "90%"
        }}>

        <p style={{ margin: "0 0 20px", color: C.text0, fontSize: 14, lineHeight: 1.6 }}>
          {message}
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={btnStyle("secondary")}>
            Cancel
          </button>
          <button onClick={onConfirm} style={btnStyle("danger")}>
            Confirm
          </button>
        </div>
      </div>
    </div>);

}

// ═══════════════════════════════════════════════════════════════════
// PANEL 1 — Flow Runs
// ═══════════════════════════════════════════════════════════════════

function FlowRunDetail({ run, onRefresh }) {
  const [history, setHistory] = useState(null);
  const [histErr, setHistErr] = useState(null);
  const [loadingHist, setLoadingHist] = useState(false);
  const [resumeEvent, setResumeEvent] = useState(run.waiting_for || "");
  const [resumePayload, setResumePayload] = useState("{}");
  const [confirm, setConfirm] = useState(null);
  const [resumeErr, setResumeErr] = useState(null);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    setLoadingHist(true);
    getFlowRunHistory(run.id).
    then((d) => setHistory(d)).
    catch((e) => setHistErr(String(e))).
    finally(() => setLoadingHist(false));
  }, [run.id]);

  const handleResume = () => {
    let payload;
    try {
      payload = JSON.parse(resumePayload);
    } catch {
      setResumeErr("Payload must be valid JSON.");
      return;
    }
    setConfirm({
      message: `Resume flow run waiting for '${resumeEvent}'? This will continue execution with the provided payload.`,
      onConfirm: async () => {
        setConfirm(null);
        setResuming(true);
        setResumeErr(null);
        try {
          await resumeFlowRun(run.id, resumeEvent, payload);
          onRefresh();
        } catch (e) {
          setResumeErr(String(e));
        } finally {
          setResuming(false);
        }
      }
    });
  };

  return (
    <div
      style={{
        background: C.bg0,
        border: `1px solid ${C.border0}`,
        borderRadius: 6,
        padding: "14px 16px",
        marginTop: 4,
        marginBottom: 8
      }}>

      {confirm &&
      <ConfirmModal
        message={confirm.message}
        onConfirm={confirm.onConfirm}
        onCancel={() => setConfirm(null)} />

      }

      {/* Error */}
      {run.error_message &&
      <div
        style={{
          padding: "8px 12px",
          background: "#441111",
          border: `1px solid ${STATUS_COLOR.failed}`,
          borderRadius: 4,
          color: "#ff8888",
          fontSize: 12,
          marginBottom: 12
        }}>

          <strong>Error:</strong> {run.error_message}
        </div>
      }

      {/* State snapshot */}
      <CollapsibleJSON label="Current execution state" data={run.state} />

      {/* History */}
      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            fontSize: 11,
            color: C.text1,
            textTransform: "uppercase",
            letterSpacing: 1,
            marginBottom: 8
          }}>

          Node History Timeline
        </div>
        {loadingHist && <LoadingState label="Loading history..." />}
        {histErr && <ErrorState error={histErr} />}
        {history && history.history.length === 0 &&
        <span style={{ fontSize: 12, color: C.text1 }}>No node history yet.</span>
        }
        {history && safeMap(
          history.history, (h, i) =>
          <div
            key={h.id || i}
            style={{
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              padding: "6px 0",
              borderBottom: `1px solid ${C.border0}`
            }}>

              <div style={STATUS_DOT_STYLE(h.status)} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                  marginBottom: 4
                }}>

                  <span style={{ fontSize: 12, color: C.text0, fontWeight: "bold" }}>
                    {h.node_name}
                  </span>
                  <StatusBadge status={h.status} />
                  {h.execution_time_ms != null &&
                <span style={{ fontSize: 11, color: C.text1 }}>
                      {h.execution_time_ms}ms
                    </span>
                }
                </div>
                {h.error_message &&
              <div style={{ fontSize: 11, color: STATUS_COLOR.failed, marginBottom: 4 }}>
                    {h.error_message}
                  </div>
              }
                <CollapsibleJSON label="Output patch" data={h.output_patch} />
              </div>
            </div>)
        }
      </div>

      {/* Resume section */}
      {run.status === "waiting" &&
      <div
        style={{
          background: C.bg1,
          border: `1px solid ${STATUS_COLOR.waiting}33`,
          borderRadius: 6,
          padding: "12px 14px"
        }}>

          <div
          style={{
            fontSize: 11,
            color: STATUS_COLOR.waiting,
            textTransform: "uppercase",
            letterSpacing: 1,
            marginBottom: 8
          }}>

            Resume Execution
          </div>
          <div style={{ fontSize: 12, color: C.text1, marginBottom: 8 }}>
            Waiting for: <strong style={{ color: C.text0 }}>{run.waiting_for}</strong>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: C.text1, display: "block", marginBottom: 4 }}>
              Event type
            </label>
            <input
            value={resumeEvent}
            onChange={(e) => setResumeEvent(e.target.value)}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: C.bg2,
              color: C.text0,
              border: `1px solid ${C.border1}`,
              borderRadius: 4,
              fontSize: 12,
              boxSizing: "border-box"
            }} />

          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: C.text1, display: "block", marginBottom: 4 }}>
              Payload (JSON)
            </label>
            <textarea
            value={resumePayload}
            onChange={(e) => setResumePayload(e.target.value)}
            rows={3}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: C.bg2,
              color: "#9f6",
              border: `1px solid ${C.border1}`,
              borderRadius: 4,
              fontSize: 11,
              fontFamily: "monospace",
              resize: "vertical",
              boxSizing: "border-box"
            }} />

          </div>
          {resumeErr &&
        <div style={{ fontSize: 12, color: STATUS_COLOR.failed, marginBottom: 8 }}>
              {resumeErr}
            </div>
        }
          <button
          onClick={handleResume}
          disabled={resuming}
          style={btnStyle("primary")}>

            {resuming ? "Resuming…" : "▶ Resume Flow"}
          </button>
        </div>
      }
    </div>);

}

function FlowRunRow({ run, onRefresh }) {
  const [expanded, setExpanded] = useState(false);

  const isActive = run.status === "running" || run.status === "waiting";
  const dur = duration(run.created_at, run.completed_at);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 12px",
          background: C.bg1,
          border: `1px solid ${C.border0}`,
          borderRadius: expanded ? "6px 6px 0 0" : 6,
          marginBottom: expanded ? 0 : 4,
          flexWrap: "wrap"
        }}>

        <div style={STATUS_DOT_STYLE(run.status)} />
        <StatusBadge status={run.status} />
        {run.workflow_type && <Badge label={run.workflow_type} />}
        <span
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 13,
            color: C.text0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap"
          }}
          title={run.flow_name}>

          {run.flow_name}
        </span>
        {run.current_node && isActive &&
        <span style={{ fontSize: 11, color: C.accent }}>@ {run.current_node}</span>
        }
        {run.waiting_for &&
        <span style={{ fontSize: 11, color: STATUS_COLOR.waiting }}>
            ⏳ {run.waiting_for}
          </span>
        }
        <span style={{ fontSize: 11, color: C.text1, whiteSpace: "nowrap" }}>
          {isActive ? `running ${dur}` : dur}
        </span>
        <span style={{ fontSize: 11, color: C.text1, whiteSpace: "nowrap" }}>
          {relativeTime(run.created_at)}
        </span>
        <button
          onClick={() => setExpanded((e) => !e)}
          style={btnStyle("secondary")}>

          {expanded ? "▲ Collapse" : "▼ Expand"}
        </button>
      </div>
      {expanded && <FlowRunDetail run={run} onRefresh={onRefresh} />}
    </div>);

}

function FlowRunsPanel({ triggerRefresh }) {
  const [runs, setRuns] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [statusFilter, setStatusFilter] = useState(null);
  const [typeFilter, setTypeFilter] = useState(null);
  const [activeStatusFilter, setActiveStatusFilter] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getFlowRuns(statusFilter || activeStatusFilter, typeFilter).
    then((d) => {
      setRuns(d);
      setLastRefreshed(new Date());
    }).
    catch((e) => setError(String(e))).
    finally(() => setLoading(false));
  }, [statusFilter, typeFilter, activeStatusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (triggerRefresh) load();
  }, [triggerRefresh, load]);

  const counts =
  runs ?
  runs.runs.reduce(
    (acc, r) => {
      acc[r.status] = (acc[r.status] || 0) + 1;
      return acc;
    },
    { running: 0, waiting: 0, success: 0, failed: 0 }
  ) :
  { running: 0, waiting: 0, success: 0, failed: 0 };

  const displayed = runs ?
  activeStatusFilter ?
  runs.runs.filter((r) => r.status === activeStatusFilter) :
  runs.runs :
  [];

  return (
    <div>
      <PanelHeader title="Flow Runs" lastRefreshed={lastRefreshed} onRefresh={load} />

      {/* Toolbar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <select
          value={statusFilter || ""}
          onChange={(e) => setStatusFilter(e.target.value || null)}
          style={selectStyle()}>

          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="waiting">Waiting</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
        </select>
        <select
          value={typeFilter || ""}
          onChange={(e) => setTypeFilter(e.target.value || null)}
          style={selectStyle()}>

          <option value="">All workflow types</option>
          <option value="arm_analysis">ARM Analysis</option>
          <option value="genesis_conversation">Genesis Conversation</option>
          <option value="genesis_lock">Genesis Lock</option>
          <option value="task_completion">Task Completion</option>
          <option value="leadgen_search">LeadGen Search</option>
        </select>
      </div>

      {/* Summary bar */}
      {runs &&
      <SummaryBar
        counts={counts}
        onFilter={setActiveStatusFilter}
        activeFilter={activeStatusFilter} />

      }

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={load} />}

      {!loading && runs && displayed.length === 0 &&
      <EmptyState
        message="No flow runs yet."
        sub="Executions appear here when you use ARM, Genesis, Tasks, or LeadGen." />

      }

      {!loading && runs && safeMap(displayed, (run) =>
      <FlowRunRow key={run.id} run={run} onRefresh={load} />)
      }
    </div>);

}

// ═══════════════════════════════════════════════════════════════════
// PANEL 2 — Automation Logs
// ═══════════════════════════════════════════════════════════════════

function AutomationLogDetail({ log, onRefresh }) {
  const [confirm, setConfirm] = useState(null);
  const [replaying, setReplaying] = useState(false);
  const [replayErr, setReplayErr] = useState(null);

  const canReplay = log.status === "failed" || log.status === "retrying";

  const handleReplay = () => {
    setConfirm({
      message: `Replay task '${log.task_name}'? The original payload will be re-submitted.`,
      onConfirm: async () => {
        setConfirm(null);
        setReplaying(true);
        setReplayErr(null);
        try {
          await replayAutomationLog(log.id);
          onRefresh();
        } catch (e) {
          setReplayErr(String(e));
        } finally {
          setReplaying(false);
        }
      }
    });
  };

  return (
    <div
      style={{
        background: C.bg0,
        border: `1px solid ${C.border0}`,
        borderRadius: 6,
        padding: "14px 16px",
        marginTop: 4,
        marginBottom: 8
      }}>

      {confirm &&
      <ConfirmModal
        message={confirm.message}
        onConfirm={confirm.onConfirm}
        onCancel={() => setConfirm(null)} />

      }

      {log.error_message &&
      <div
        style={{
          padding: "8px 12px",
          background: "#441111",
          border: `1px solid ${STATUS_COLOR.failed}`,
          borderRadius: 4,
          color: "#ff8888",
          fontSize: 12,
          marginBottom: 12
        }}>

          <strong>Error:</strong> {log.error_message}
        </div>
      }

      <CollapsibleJSON label="Payload" data={log.payload} />
      <CollapsibleJSON label="Result" data={log.result} />

      <div
        style={{
          fontSize: 11,
          color: C.text1,
          textTransform: "uppercase",
          letterSpacing: 1,
          marginBottom: 8,
          marginTop: 8
        }}>

        Timeline
      </div>
      <div style={{ fontSize: 12, color: C.text1, display: "flex", flexDirection: "column", gap: 4 }}>
        <div>
          Created: <span style={{ color: C.text0 }}>{log.created_at || "—"}</span>
        </div>
        <div>
          Started: <span style={{ color: C.text0 }}>{log.started_at || "not started"}</span>
        </div>
        <div>
          Completed: <span style={{ color: C.text0 }}>{log.completed_at || "in progress"}</span>
        </div>
      </div>

      {replayErr &&
      <div style={{ fontSize: 12, color: STATUS_COLOR.failed, marginTop: 8 }}>{replayErr}</div>
      }

      {canReplay &&
      <button
        onClick={handleReplay}
        disabled={replaying}
        style={{ ...btnStyle("danger"), marginTop: 12 }}>

          {replaying ? "Replaying…" : "🔁 Replay Task"}
        </button>
      }
    </div>);

}

function AutomationLogRow({ log, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const canReplay = log.status === "failed" || log.status === "retrying";
  const dur = duration(log.started_at, log.completed_at);
  const multiAttempt = log.attempt_count > 1;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 12px",
          background: C.bg1,
          border: `1px solid ${C.border0}`,
          borderRadius: expanded ? "6px 6px 0 0" : 6,
          marginBottom: expanded ? 0 : 4,
          flexWrap: "wrap"
        }}>

        <div style={STATUS_DOT_STYLE(log.status)} />
        <StatusBadge status={log.status} />
        {log.source && <Badge label={log.source} />}
        <span
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 13,
            color: C.text0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap"
          }}>

          {log.task_name || "—"}
        </span>
        <span
          style={{
            fontSize: 11,
            color: multiAttempt ? STATUS_COLOR.retrying : C.text1,
            whiteSpace: "nowrap"
          }}>

          {multiAttempt ? "⚠ " : ""}
          {log.attempt_count}/{log.max_attempts}
        </span>
        <span style={{ fontSize: 11, color: C.text1, whiteSpace: "nowrap" }}>{dur}</span>
        <span style={{ fontSize: 11, color: C.text1, whiteSpace: "nowrap" }}>
          {relativeTime(log.created_at)}
        </span>
        {log.error_message &&
        <span style={{ fontSize: 11, color: STATUS_COLOR.failed }}>
            {truncate(log.error_message, 60)}
          </span>
        }
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setExpanded((e) => !e)} style={btnStyle("secondary")}>
            {expanded ? "▲" : "👁"}
          </button>
        </div>
      </div>
      {expanded && <AutomationLogDetail log={log} onRefresh={onRefresh} />}
    </div>);

}

function SchedulerStatusBar({ triggerRefresh }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getSchedulerStatus().
    then((d) => {
      setStatus(d);
      setLastRefreshed(new Date());
    }).
    catch((e) => setError(String(e))).
    finally(() => setLoading(false));
  }, []);

  useEffect(() => {load();}, [load]);
  useEffect(() => {if (triggerRefresh) load();}, [triggerRefresh, load]);

  return (
    <div
      style={{
        background: C.bg1,
        border: `1px solid ${C.border0}`,
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 16
      }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 12, color: C.text1, textTransform: "uppercase", letterSpacing: 1 }}>
            APScheduler
          </span>
          {loading && <span style={{ fontSize: 12, color: C.text1 }}>Loading…</span>}
          {error && <span style={{ fontSize: 12, color: STATUS_COLOR.failed }}>{error}</span>}
          {status &&
          <>
              <span style={{ fontSize: 12, color: status.running ? STATUS_COLOR.success : STATUS_COLOR.failed }}>
                {status.running ? "✅ Running" : "❌ Stopped"}
              </span>
              <span style={{ fontSize: 12, color: C.text1 }}>
                {status.job_count} job{status.job_count !== 1 ? "s" : ""} registered
              </span>
              {status.job_count > 0 &&
            <button
              onClick={() => setJobsOpen((o) => !o)}
              style={{ background: "none", border: "none", color: C.accent, cursor: "pointer", fontSize: 12 }}>

                  {jobsOpen ? "▼ Hide jobs" : "▶ Show jobs"}
                </button>
            }
            </>
          }
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {lastRefreshed &&
          <span style={{ fontSize: 11, color: C.text1 }}>
              {relativeTime(lastRefreshed)}
            </span>
          }
          <button onClick={load} style={btnStyle("secondary")}>🔄</button>
        </div>
      </div>

      {jobsOpen && status && status.jobs.length > 0 &&
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          {safeMap(status.jobs, (job) =>
        <div
          key={job.id}
          style={{
            display: "flex",
            gap: 10,
            fontSize: 12,
            color: C.text1,
            borderTop: `1px solid ${C.border0}`,
            paddingTop: 6
          }}>

              <span style={{ color: C.text0, fontWeight: "bold" }}>{job.name || job.id}</span>
              <span>{job.trigger}</span>
              {job.next_run &&
          <span style={{ color: C.accent }}>Next: {relativeTime(job.next_run)}</span>
          }
            </div>)
        }
        </div>
      }
    </div>);

}

function AutomationPanel({ triggerRefresh }) {
  const [logs, setLogs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [statusFilter, setStatusFilter] = useState(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [activeStatusFilter, setActiveStatusFilter] = useState(null);
  const [replayingAll, setReplayingAll] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getAutomationLogs(statusFilter, sourceFilter || null).
    then((d) => {
      setLogs(d);
      setLastRefreshed(new Date());
    }).
    catch((e) => setError(String(e))).
    finally(() => setLoading(false));
  }, [statusFilter, sourceFilter]);

  useEffect(() => {load();}, [load]);
  useEffect(() => {if (triggerRefresh) load();}, [triggerRefresh, load]);

  const counts =
  logs ?
  logs.logs.reduce(
    (acc, l) => {
      acc[l.status] = (acc[l.status] || 0) + 1;
      return acc;
    },
    { pending: 0, running: 0, success: 0, failed: 0, retrying: 0 }
  ) :
  { pending: 0, running: 0, success: 0, failed: 0, retrying: 0 };

  const displayed = logs ?
  activeStatusFilter ?
  logs.logs.filter((l) => l.status === activeStatusFilter) :
  logs.logs :
  [];

  const failedLogs = logs ? logs.logs.filter((l) => l.status === "failed") : [];

  const replayAll = async () => {
    setReplayingAll(true);
    try {
      await Promise.all(safeMap(failedLogs, (l) => replayAutomationLog(l.id)));
      load();
    } catch {

      /* individual errors handled per-row */} finally {
      setReplayingAll(false);
    }
  };

  return (
    <div>
      <SchedulerStatusBar triggerRefresh={triggerRefresh} />

      <PanelHeader title="Automation Logs" lastRefreshed={lastRefreshed} onRefresh={load} />

      {/* Toolbar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <select
          value={statusFilter || ""}
          onChange={(e) => setStatusFilter(e.target.value || null)}
          style={selectStyle()}>

          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="running">Running</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="retrying">Retrying</option>
        </select>
        <input
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          placeholder="Filter by source…"
          style={{
            padding: "5px 8px",
            background: C.bg2,
            color: C.text0,
            border: `1px solid ${C.border1}`,
            borderRadius: 5,
            fontSize: 12,
            width: 160
          }} />

      </div>

      {/* Summary bar */}
      {logs &&
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
          <SummaryBar
          counts={counts}
          onFilter={setActiveStatusFilter}
          activeFilter={activeStatusFilter} />

          {failedLogs.length > 0 &&
        <button
          onClick={replayAll}
          disabled={replayingAll}
          style={btnStyle("danger")}>

              {replayingAll ? "Replaying…" : `🔁 Replay all failed (${failedLogs.length})`}
            </button>
        }
        </div>
      }

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={load} />}

      {!loading && logs && displayed.length === 0 &&
      <EmptyState
        message="No automation logs yet."
        sub="Background task executions will appear here." />

      }

      {!loading && logs && safeMap(displayed, (log) =>
      <AutomationLogRow key={log.id} log={log} onRefresh={load} />)
      }
    </div>);

}

// ═══════════════════════════════════════════════════════════════════
// PANEL 3 — Registry
// ═══════════════════════════════════════════════════════════════════

function FlowGraph({ flowName, registry }) {
  const flow = registry.flows[flowName];
  if (!flow) return null;

  // Build a simple linear node chain from start node
  // We derive a path heuristically from start node
  const startNode = flow.start;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 4,
        padding: "10px 0",
        overflowX: "auto"
      }}>

      <NodeBox name={startNode} />
      <span style={{ color: C.text1, fontSize: 14 }}>→</span>
      {flow.end && flow.end.length > 0 ? safeMap(
        flow.end, (endNode, i) =>
        <React.Fragment key={endNode}>
            {i > 0 && <span style={{ color: C.text1, fontSize: 14 }}>⑂</span>}
            <NodeBox name={endNode} />
          </React.Fragment>) :


      <span style={{ color: C.text1, fontSize: 12 }}>… ({flow.node_count} nodes)</span>
      }
    </div>);

}

function NodeBox({ name, highlighted }) {
  return (
    <div
      style={{
        padding: "5px 10px",
        background: highlighted ? "#1a2a1a" : C.bg0,
        border: `1px solid ${highlighted ? STATUS_COLOR.success : C.border1}`,
        borderRadius: 4,
        fontSize: 11,
        color: highlighted ? STATUS_COLOR.success : C.text0,
        fontFamily: "monospace",
        whiteSpace: "nowrap"
      }}>

      {name}
    </div>);

}

function FlowCard({ flowName, registry, highlightedNode }) {
  const [expanded, setExpanded] = useState(false);
  const flow = registry.flows[flowName];
  if (!flow) return null;

  return (
    <div
      style={{
        background: C.bg1,
        border: `1px solid ${C.border0}`,
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 8
      }}>

      <div
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 14, color: C.text0, fontWeight: "bold" }}>{flowName}</span>
          <Badge label={`${flow.node_count} nodes`} />
        </div>
        <button onClick={() => setExpanded((e) => !e)} style={btnStyle("secondary")}>
          {expanded ? "▲ Collapse" : "▶ Expand"}
        </button>
      </div>

      <div style={{ fontSize: 12, color: C.text1, marginTop: 6 }}>
        <span style={{ color: C.accent }}>{flow.start}</span>
        {" → … → "}
        {flow.end && flow.end.length > 0 ?
        flow.end.join(", ") :

        <span style={{ color: C.text1 }}>—</span>
        }
      </div>

      {expanded && <FlowGraph flowName={flowName} registry={registry} />}
    </div>);

}

function RegistryPanel({ triggerRefresh }) {
  const [registry, setRegistry] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [nodesOpen, setNodesOpen] = useState(false);
  const [highlightedNode, setHighlightedNode] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getFlowRegistry().
    then((d) => {
      setRegistry(d);
      setLastRefreshed(new Date());
    }).
    catch((e) => setError(String(e))).
    finally(() => setLoading(false));
  }, []);

  useEffect(() => {load();}, [load]);
  useEffect(() => {if (triggerRefresh) load();}, [triggerRefresh, load]);

  return (
    <div>
      <PanelHeader
        title="Execution Topology"
        lastRefreshed={lastRefreshed}
        onRefresh={load}>

        {registry &&
        <span style={{ fontSize: 12, color: C.text1 }}>
            {registry.flow_count} flows · {registry.node_count} nodes registered
          </span>
        }
      </PanelHeader>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={load} />}

      {!loading && registry && Object.keys(registry.flows).length === 0 &&
      <EmptyState
        message="No flows registered yet."
        sub="Flows appear here when the flow engine is initialized." />

      }

      {!loading && registry && safeMap(Object.keys(registry.flows), (flowName) =>
      <FlowCard
        key={flowName}
        flowName={flowName}
        registry={registry}
        highlightedNode={highlightedNode} />)

      }

      {/* Node registry */}
      {registry && registry.nodes.length > 0 &&
      <div
        style={{
          background: C.bg1,
          border: `1px solid ${C.border0}`,
          borderRadius: 8,
          padding: "12px 16px",
          marginTop: 12
        }}>

          <button
          onClick={() => setNodesOpen((o) => !o)}
          style={{
            background: "none",
            border: "none",
            color: C.text0,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: "bold",
            padding: 0
          }}>

            {nodesOpen ? "▼" : "▶"} All registered nodes ({registry.nodes.length})
          </button>
          {nodesOpen &&
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {safeMap(registry.nodes, (node) =>
          <button
            key={node}
            onClick={() =>
            setHighlightedNode(highlightedNode === node ? null : node)
            }
            style={{
              padding: "4px 10px",
              background:
              highlightedNode === node ? "#1a2a1a" : C.bg0,
              border: `1px solid ${
              highlightedNode === node ?
              STATUS_COLOR.success :
              C.border1}`,

              borderRadius: 12,
              fontSize: 11,
              color:
              highlightedNode === node ?
              STATUS_COLOR.success :
              C.text0,
              cursor: "pointer",
              fontFamily: "monospace"
            }}>

                  {node}
                </button>)
          }
            </div>
        }
        </div>
      }
    </div>);

}

// ═══════════════════════════════════════════════════════════════════
// PANEL 4 — Strategies
// ═══════════════════════════════════════════════════════════════════

function ScoreBar({ score }) {
  const max = 2.0;
  const pct = Math.min(100, score / max * 100);
  const color =
  score > 1.0 ?
  STATUS_COLOR.success :
  score >= 0.5 ?
  STATUS_COLOR.waiting :
  STATUS_COLOR.failed;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: C.border0,
          borderRadius: 3,
          overflow: "hidden"
        }}>

        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            transition: "width 0.3s"
          }} />

      </div>
      <span style={{ fontSize: 11, color, minWidth: 28, textAlign: "right" }}>
        {score.toFixed(2)}
      </span>
    </div>);

}

function StrategyCard({ strategy }) {
  const [expanded, setExpanded] = useState(false);
  const isSystem = !strategy.user_id;
  const successRate =
  strategy.usage_count > 0 ?
  Math.round(strategy.success_count / strategy.usage_count * 100) :
  null;

  return (
    <div
      style={{
        background: C.bg1,
        border: `1px solid ${C.border0}`,
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 8
      }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Badge label={strategy.intent_type} color={C.accent} />
          <Badge label={isSystem ? "system" : "user"} color={isSystem ? "#9f6" : "#f6f"} />
        </div>
        <button onClick={() => setExpanded((e) => !e)} style={btnStyle("secondary")}>
          {expanded ? "▲" : "▶"}
        </button>
      </div>

      <div style={{ marginTop: 10 }}>
        <ScoreBar score={strategy.score} />
      </div>

      <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: C.text1 }}>
          Used{" "}
          <strong style={{ color: C.text0 }}>{strategy.usage_count}</strong>{" "}
          time{strategy.usage_count !== 1 ? "s" : ""}
        </span>
        {successRate !== null &&
        <span style={{ fontSize: 12, color: C.text1 }}>
            <strong style={{ color: STATUS_COLOR.success }}>{successRate}%</strong> success
          </span>
        }
      </div>

      {expanded &&
      <div style={{ marginTop: 10 }}>
          <CollapsibleJSON label="Flow definition" data={strategy.flow} />
        </div>
      }
    </div>);

}

function StrategiesPanel({ triggerRefresh }) {
  const [strategies, setStrategies] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  // Strategies are fetched from the flow runs with strategy data embedded.
  // The backend doesn't expose a /flows/strategies endpoint yet, so we note
  // this is a future endpoint. For now we show empty state gracefully.
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    // Attempt to call strategies endpoint; gracefully handle 404/not-implemented
    fetch(buildApiUrl("/flows/strategies"), {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("aindy_token") || ""}`
      }
    }).
    then(async (res) => {
      if (res.status === 404 || res.status === 405) {
        setStrategies({ strategies: [], count: 0 });
        return;
      }
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`API Error (${res.status}): ${t}`);
      }
      const data = await res.json();
      setStrategies(data);
    }).
    catch(() => {
      // Endpoint doesn't exist yet — show empty state
      setStrategies({ strategies: [], count: 0 });
    }).
    finally(() => {
      setLastRefreshed(new Date());
      setLoading(false);
    });
  }, []);

  useEffect(() => {load();}, [load]);
  useEffect(() => {if (triggerRefresh) load();}, [triggerRefresh, load]);

  return (
    <div>
      <PanelHeader title="Learned Strategies" lastRefreshed={lastRefreshed} onRefresh={load}>
        <span style={{ fontSize: 12, color: C.text1 }}>
          The engine learns which flows work best for each workflow type over time.
        </span>
      </PanelHeader>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={load} />}

      {!loading && strategies && strategies.strategies.length === 0 &&
      <EmptyState
        message="No learned strategies yet."
        sub={
        "Strategies are created automatically as A.I.N.D.Y. learns which execution flows work best for each workflow type.\n\nRun ARM analysis, Genesis sessions, and task completions to build the strategy library."
        } />

      }

      {!loading &&
      strategies && safeMap(
        strategies.strategies, (s) =>
        <StrategyCard key={s.id} strategy={s} />)
      }
    </div>);

}

// ═══════════════════════════════════════════════════════════════════
// TOP-LEVEL: FlowEngineConsole
// ═══════════════════════════════════════════════════════════════════

const TABS = [
{ id: "runs", label: "Flow Runs" },
{ id: "automation", label: "Automation" },
{ id: "registry", label: "Registry" },
{ id: "strategies", label: "Strategies" }];


export default function FlowEngineConsole() {
  const [activeTab, setActiveTab] = useState("runs");
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const handleRefreshAll = () => {
    setRefreshTick((t) => t + 1);
    setLastRefreshed(new Date());
  };

  return (
    <div
      style={{
        padding: "20px",
        color: C.text0,
        fontFamily: "sans-serif",
        maxWidth: 1000
      }}>

      {/* Console header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
          flexWrap: "wrap",
          gap: 10
        }}>

        <h2 style={{ margin: 0, color: "#fff" }}>Execution Console</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {lastRefreshed &&
          <span style={{ fontSize: 12, color: C.text1 }}>
              Last refreshed: {relativeTime(lastRefreshed)}
            </span>
          }
          <button onClick={handleRefreshAll} style={btnStyle("primary")}>
            🔄 Refresh all
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: 2,
          marginBottom: 20,
          borderBottom: `1px solid ${C.border0}`,
          paddingBottom: 0
        }}>

        {safeMap(TABS, (tab) =>
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          style={{
            padding: "8px 18px",
            background: "none",
            border: "none",
            borderBottom:
            activeTab === tab.id ?
            `2px solid ${C.accent}` :
            "2px solid transparent",
            color: activeTab === tab.id ? C.accent : C.text1,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: activeTab === tab.id ? "bold" : "normal",
            transition: "color 0.15s"
          }}>

            {tab.label}
          </button>)
        }
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "runs" &&
        <FlowRunsPanel triggerRefresh={refreshTick} />
        }
        {activeTab === "automation" &&
        <AutomationPanel triggerRefresh={refreshTick} />
        }
        {activeTab === "registry" &&
        <RegistryPanel triggerRefresh={refreshTick} />
        }
        {activeTab === "strategies" &&
        <StrategiesPanel triggerRefresh={refreshTick} />
        }
      </div>
    </div>);

}