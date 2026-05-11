import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getAgents() {
  return authRequest(ROUTES.MEMORY.AGENTS, { method: "GET" });
}

export function recallFromAgent(namespace, query = "", limit = 5) {
  return authRequest(
    `${ROUTES.MEMORY.AGENT_RECALL(namespace)}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { method: "GET" }
  );
}

export function getFederatedMemory(query, namespaces = null, limit = 5) {
  return authRequest(ROUTES.MEMORY.FEDERATED_RECALL, {
    method: "POST",
    body: JSON.stringify({ query, agent_namespaces: namespaces, limit }),
  });
}

export function createAgentRun(payload) {
  return authRequest(ROUTES.AGENT.CREATE_RUN, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentRuns(status = null, limit = 20) {
  const params = new URLSearchParams({ limit });
  if (status) params.append("status", status);
  return authRequest(`${ROUTES.AGENT.RUNS}?${params.toString()}`, { method: "GET" });
}

export function getAgentRun(runId) {
  return authRequest(ROUTES.AGENT.RUN(runId), { method: "GET" });
}

export function approveAgentRun(runId) {
  return authRequest(ROUTES.AGENT.APPROVE(runId), { method: "POST" });
}

export function rejectAgentRun(runId) {
  return authRequest(ROUTES.AGENT.REJECT(runId), { method: "POST" });
}

export function getAgentRunSteps(runId) {
  return authRequest(ROUTES.AGENT.STEPS(runId), { method: "GET" });
}

export function getAgentTools() {
  return authRequest(ROUTES.AGENT.TOOLS, { method: "GET" });
}

export function getAgentTrust() {
  return authRequest(ROUTES.AGENT.TRUST, { method: "GET" });
}

export function updateAgentTrust(payload) {
  return authRequest(ROUTES.AGENT.TRUST, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAgentSuggestions() {
  return authRequest(ROUTES.AGENT.SUGGESTIONS, { method: "GET" });
}

export async function fetchRunEvents(runId) {
  return authRequest(ROUTES.AGENT.EVENTS(runId));
}
