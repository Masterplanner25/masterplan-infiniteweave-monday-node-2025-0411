import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export * from "./operator.js";

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
