import { authRequest } from "./_core.js";

export function getMemoryNodes(tags = [], limit = 20) {
  const tagParam = tags.length ? `&tags=${tags.join(",")}` : "";
  return authRequest(`/memory/nodes?limit=${limit}${tagParam}`, { method: "GET" });
}

export function recallMemory(query, tags = [], limit = 5, expandResults = false) {
  return authRequest("/memory/recall/v3", {
    method: "POST",
    body: JSON.stringify({ query, tags, limit, expand_results: expandResults }),
  });
}

export function getMemorySuggestions(query, tags = [], limit = 3) {
  return authRequest("/memory/suggest", {
    method: "POST",
    body: JSON.stringify({ query, tags, limit }),
  });
}

export function recordMemoryFeedback(nodeId, outcome, context = "") {
  return authRequest(`/memory/nodes/${nodeId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ outcome, context }),
  });
}

export function getNodePerformance(nodeId) {
  return authRequest(`/memory/nodes/${nodeId}/performance`, { method: "GET" });
}

export function traverseMemory(nodeId, maxDepth = 3) {
  return authRequest(`/memory/nodes/${nodeId}/traverse?max_depth=${maxDepth}`, { method: "GET" });
}

export function getNodeHistory(nodeId, limit = 10) {
  return authRequest(`/memory/nodes/${nodeId}/history?limit=${limit}`, { method: "GET" });
}

export function getFederatedRecall(query, tags = [], agentNamespaces = null, limit = 5) {
  return authRequest("/memory/federated/recall", {
    method: "POST",
    body: JSON.stringify({ query, tags, agent_namespaces: agentNamespaces, limit }),
  });
}

export function shareMemoryNode(nodeId) {
  return authRequest(`/memory/nodes/${nodeId}/share`, { method: "POST" });
}

export function getMemoryMetricsDashboard() {
  return authRequest("/memory/metrics/dashboard", { method: "GET" });
}
