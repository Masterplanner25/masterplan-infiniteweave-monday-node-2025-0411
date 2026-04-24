import { authRequest } from "./_core.js";

export function getFlowRuns(status = null, workflowType = null, limit = 20) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (workflowType) params.append("workflow_type", workflowType);
  params.append("limit", limit);
  return authRequest(`/flows/runs?${params.toString()}`, { method: "GET" });
}

export function getFlowRun(runId) {
  return authRequest(`/flows/runs/${runId}`, { method: "GET" });
}

export function getFlowRunHistory(runId) {
  return authRequest(`/flows/runs/${runId}/history`, { method: "GET" });
}

export function resumeFlowRun(runId, eventType, payload = {}) {
  return authRequest(`/flows/runs/${runId}/resume`, {
    method: "POST",
    body: JSON.stringify({ event_type: eventType, payload }),
  });
}

export function getFlowRegistry() {
  return authRequest("/flows/registry", { method: "GET" });
}

export function getFlowStrategies() {
  return authRequest("/flows/strategies", { method: "GET" });
}

export function getAutomationLogs(status = null, source = null, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (source) params.append("source", source);
  params.append("limit", limit);
  return authRequest(`/automation/logs?${params.toString()}`, { method: "GET" });
}

export function getAutomationLog(logId) {
  return authRequest(`/automation/logs/${logId}`, { method: "GET" });
}

export function replayAutomationLog(logId) {
  return authRequest(`/automation/logs/${logId}/replay`, { method: "POST" });
}

export function getSchedulerStatus() {
  return authRequest("/automation/scheduler/status", { method: "GET" });
}

export function getObservabilityRequests(windowHours = 24, limit = 50, errorLimit = 25) {
  const params = new URLSearchParams({
    window_hours: String(windowHours),
    limit: String(limit),
    error_limit: String(errorLimit),
  });
  return authRequest(`/observability/requests?${params.toString()}`, { method: "GET" });
}

export function getObservabilityDashboard(windowHours = 24) {
  const params = new URLSearchParams({
    window_hours: String(windowHours),
  });
  return authRequest(`/observability/dashboard?${params.toString()}`, { method: "GET" });
}

export async function reportClientError(payload) {
  await authRequest("/client/error", {
    method: "POST",
    body: JSON.stringify(payload),
  }).catch(() => {});
}

export async function reportClientVitals(payload) {
  await authRequest("/client/vitals", {
    method: "POST",
    body: JSON.stringify(payload),
  }).catch(() => {});
}
