import { authRequest } from "./_core.js";

export function getAgents() {
  return authRequest("/memory/agents", { method: "GET" });
}

export function recallFromAgent(namespace, query = "", limit = 5) {
  return authRequest(
    `/memory/agents/${namespace}/recall?query=${encodeURIComponent(query)}&limit=${limit}`,
    { method: "GET" }
  );
}

export function getFederatedMemory(query, namespaces = null, limit = 5) {
  return authRequest("/memory/federated/recall", {
    method: "POST",
    body: JSON.stringify({ query, agent_namespaces: namespaces, limit }),
  });
}

export function createAgentRun(payload) {
  return authRequest("/agent/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentRuns(status = null, limit = 20) {
  const params = new URLSearchParams({ limit });
  if (status) params.append("status", status);
  return authRequest(`/agent/runs?${params.toString()}`, { method: "GET" });
}

export function getAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}`, { method: "GET" });
}

export function approveAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}/approve`, { method: "POST" });
}

export function rejectAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}/reject`, { method: "POST" });
}

export function getAgentRunSteps(runId) {
  return authRequest(`/agent/runs/${runId}/steps`, { method: "GET" });
}

export function getAgentTools() {
  return authRequest("/agent/tools", { method: "GET" });
}

export function getAgentTrust() {
  return authRequest("/agent/trust", { method: "GET" });
}

export function updateAgentTrust(payload) {
  return authRequest("/agent/trust", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAgentSuggestions() {
  return authRequest("/agent/suggestions", { method: "GET" });
}

export async function fetchRunEvents(runId) {
  return authRequest(`/agent/runs/${runId}/events`);
}
