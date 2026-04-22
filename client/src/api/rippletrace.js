import { authRequest } from "./_core.js";

export function getRippleDropPoints() {
  return authRequest("/rippletrace/drop_points", { method: "GET" });
}

export function getRipplePings() {
  return authRequest("/rippletrace/pings", { method: "GET" });
}

export function getRecentRippleEvents(limit = 20) {
  return authRequest(`/rippletrace/recent?limit=${limit}`, { method: "GET" });
}

export function getRippleTrace(dropPointId) {
  return authRequest(`/rippletrace/ripples/${dropPointId}`, { method: "GET" });
}

export function getRippleTraceGraph(traceId) {
  return authRequest(`/rippletrace/${encodeURIComponent(traceId)}`, { method: "GET" });
}
