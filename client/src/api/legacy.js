import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

// Legacy or mixed-surface routes still used by the product UI.
// These are not operator/runtime APIs, but they also do not fit the newer
// domain API split cleanly yet because the backend ownership is still mixed.

export function getDashboardOverview() {
  return authRequest(ROUTES.PLATFORM.DASHBOARD_OVERVIEW, { method: "GET" });
}

export function getDashboardHealth() {
  return authRequest(ROUTES.PLATFORM.DASHBOARD_HEALTH, { method: "GET" });
}

export function getInfluenceGraph() {
  return authRequest(ROUTES.PLATFORM.INFLUENCE_GRAPH, { method: "GET" });
}

export function getCausalGraph() {
  return authRequest(ROUTES.PLATFORM.CAUSAL_GRAPH, { method: "GET" });
}

export function getNarrative(dropPointId) {
  return authRequest(ROUTES.PLATFORM.NARRATIVE(dropPointId), { method: "GET" });
}
