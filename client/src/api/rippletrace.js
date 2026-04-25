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

export function getCausalGraph() {
  return authRequest("/rippletrace/causal/graph");
}

export function getCausalChain(dropPointId, depth = 3) {
  return authRequest(
    `/rippletrace/causal/chain/${encodeURIComponent(dropPointId)}?depth=${depth}`
  );
}

export function getNarrativeSummary(limit = 3) {
  return authRequest(`/rippletrace/narrative/summary?limit=${limit}`);
}

export function getDropPointNarrative(dropPointId) {
  return authRequest(
    `/rippletrace/narrative/${encodeURIComponent(dropPointId)}`
  );
}

export function getPredictionsSummary(limit = 50) {
  return authRequest(`/rippletrace/predictions/summary?limit=${limit}`);
}

export function getDropPointPrediction(dropPointId, recordLearning = true) {
  return authRequest(
    `/rippletrace/predictions/${encodeURIComponent(dropPointId)}` +
      `?record_learning=${recordLearning}`
  );
}

export function getSystemRecommendations(limit = 20) {
  return authRequest(`/rippletrace/recommendations/system?limit=${limit}`);
}

export function getRecommendationsSummary(limit = 20) {
  return authRequest(`/rippletrace/recommendations/summary?limit=${limit}`);
}

export function getDropPointRecommendation(dropPointId) {
  return authRequest(
    `/rippletrace/recommendations/${encodeURIComponent(dropPointId)}`
  );
}

export function getLearningStats() {
  return authRequest("/rippletrace/learning/stats");
}

export function evaluateLearningOutcome(dropPointId) {
  return authRequest(
    `/rippletrace/learning/evaluate/${encodeURIComponent(dropPointId)}`,
    { method: "POST" }
  );
}

export function adjustLearningThresholds() {
  return authRequest("/rippletrace/learning/adjust", { method: "POST" });
}

export function getPlaybooks() {
  return authRequest("/rippletrace/playbooks");
}

export function getPlaybook(playbookId) {
  return authRequest(
    `/rippletrace/playbooks/${encodeURIComponent(playbookId)}`
  );
}

export function matchPlaybooks(dropPointId) {
  return authRequest(
    `/rippletrace/playbooks/match/${encodeURIComponent(dropPointId)}`
  );
}

export function getStrategies() {
  return authRequest("/rippletrace/strategies");
}

export function buildStrategies() {
  return authRequest("/rippletrace/strategies/build");
}

export function getStrategy(strategyId) {
  return authRequest(
    `/rippletrace/strategies/${encodeURIComponent(strategyId)}`
  );
}

export function matchStrategies(dropPointId) {
  return authRequest(
    `/rippletrace/strategies/match/${encodeURIComponent(dropPointId)}`
  );
}

export function getEventDownstream(eventId) {
  return authRequest(
    `/rippletrace/event/${encodeURIComponent(eventId)}/downstream`
  );
}

export function getEventUpstream(eventId) {
  return authRequest(
    `/rippletrace/event/${encodeURIComponent(eventId)}/upstream`
  );
}
