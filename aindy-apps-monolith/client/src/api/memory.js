import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getMemoryNodes(tags = [], limit = 20) {
  const tagParam = tags.length ? `&tags=${tags.join(",")}` : "";
  return authRequest(`${ROUTES.MEMORY.NODES}?limit=${limit}${tagParam}`, { method: "GET" });
}

export function recallMemory(query, tags = [], limit = 5, expandResults = false) {
  return authRequest(ROUTES.MEMORY.RECALL_V3, {
    method: "POST",
    body: JSON.stringify({ query, tags, limit, expand_results: expandResults }),
  });
}

export function getMemorySuggestions(query, tags = [], limit = 3) {
  return authRequest(ROUTES.MEMORY.SUGGEST, {
    method: "POST",
    body: JSON.stringify({ query, tags, limit }),
  });
}

export function recordMemoryFeedback(nodeId, outcome, context = "") {
  return authRequest(ROUTES.MEMORY.NODE_FEEDBACK(nodeId), {
    method: "POST",
    body: JSON.stringify({ outcome, context }),
  });
}

export function getNodePerformance(nodeId) {
  return authRequest(ROUTES.MEMORY.NODE_PERFORMANCE(nodeId), { method: "GET" });
}

export function traverseMemory(nodeId, maxDepth = 3) {
  return authRequest(`${ROUTES.MEMORY.NODE_TRAVERSE(nodeId)}?max_depth=${maxDepth}`, { method: "GET" });
}

export function getNodeHistory(nodeId, limit = 10) {
  return authRequest(`${ROUTES.MEMORY.NODE_HISTORY(nodeId)}?limit=${limit}`, { method: "GET" });
}

export function getFederatedRecall(query, tags = [], agentNamespaces = null, limit = 5) {
  return authRequest(ROUTES.MEMORY.FEDERATED_RECALL, {
    method: "POST",
    body: JSON.stringify({ query, tags, agent_namespaces: agentNamespaces, limit }),
  });
}

export function shareMemoryNode(nodeId) {
  return authRequest(ROUTES.MEMORY.NODE_SHARE(nodeId), { method: "POST" });
}

export function getMemoryMetricsDashboard() {
  return authRequest(ROUTES.MEMORY.METRICS_DASHBOARD, { method: "GET" });
}
