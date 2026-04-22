import { authRequest } from "./_core.js";

// Legacy or mixed-surface routes still used by the product UI.
// These are not operator/runtime APIs, but they also do not fit the newer
// domain API split cleanly yet because the backend ownership is still mixed.

export function getDashboardOverview() {
  return authRequest("/dashboard/overview", { method: "GET" });
}

export function getDashboardHealth() {
  return authRequest("/dashboard/health", { method: "GET" });
}

export function getInfluenceGraph() {
  return authRequest("/influence_graph", { method: "GET" });
}

export function getCausalGraph() {
  return authRequest("/causal_graph", { method: "GET" });
}

export function getNarrative(dropPointId) {
  return authRequest(`/narrative/${dropPointId}`, { method: "GET" });
}
