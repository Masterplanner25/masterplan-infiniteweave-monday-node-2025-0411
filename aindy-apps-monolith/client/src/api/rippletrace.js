import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getRippleDropPoints() {
  return authRequest(ROUTES.RIPPLETRACE.DROP_POINTS, { method: "GET" });
}

export function getRipplePings() {
  return authRequest(ROUTES.RIPPLETRACE.PINGS, { method: "GET" });
}

export function getRecentRippleEvents(limit = 20) {
  return authRequest(`${ROUTES.RIPPLETRACE.RECENT}?limit=${limit}`, { method: "GET" });
}

export function getRippleTrace(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.TRACE(dropPointId), { method: "GET" });
}

export function getRippleTraceGraph(traceId) {
  return authRequest(ROUTES.RIPPLETRACE.TRACE_GRAPH(traceId), { method: "GET" });
}

export function getCausalGraph() {
  return authRequest(ROUTES.RIPPLETRACE.CAUSAL_GRAPH);
}

export function getCausalChain(dropPointId, depth = 3) {
  return authRequest(`${ROUTES.RIPPLETRACE.CAUSAL_CHAIN(dropPointId)}?depth=${depth}`);
}

export function getNarrativeSummary(limit = 3) {
  return authRequest(`${ROUTES.RIPPLETRACE.NARRATIVE_SUMMARY}?limit=${limit}`);
}

export function getDropPointNarrative(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.DROP_POINT_NARRATIVE(dropPointId));
}

export function getPredictionsSummary(limit = 50) {
  return authRequest(`${ROUTES.RIPPLETRACE.PREDICTIONS_SUMMARY}?limit=${limit}`);
}

export function getDropPointPrediction(dropPointId, recordLearning = true) {
  return authRequest(
    ROUTES.RIPPLETRACE.DROP_POINT_PREDICTION(dropPointId) +
      `?record_learning=${recordLearning}`
  );
}

export function getSystemRecommendations(limit = 20) {
  return authRequest(`${ROUTES.RIPPLETRACE.SYSTEM_RECOMMENDATIONS}?limit=${limit}`);
}

export function getRecommendationsSummary(limit = 20) {
  return authRequest(`${ROUTES.RIPPLETRACE.RECOMMENDATIONS_SUMMARY}?limit=${limit}`);
}

export function getDropPointRecommendation(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.DROP_POINT_RECOMMENDATION(dropPointId));
}

export function getLearningStats() {
  return authRequest(ROUTES.RIPPLETRACE.LEARNING_STATS);
}

export function evaluateLearningOutcome(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.EVALUATE_LEARNING_OUTCOME(dropPointId), {
    method: "POST",
  });
}

export function adjustLearningThresholds() {
  return authRequest(ROUTES.RIPPLETRACE.ADJUST_LEARNING_THRESHOLDS, { method: "POST" });
}

export function getPlaybooks() {
  return authRequest(ROUTES.RIPPLETRACE.PLAYBOOKS);
}

export function getPlaybook(playbookId) {
  return authRequest(ROUTES.RIPPLETRACE.PLAYBOOK(playbookId));
}

export function matchPlaybooks(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.MATCH_PLAYBOOKS(dropPointId));
}

export function getStrategies() {
  return authRequest(ROUTES.RIPPLETRACE.STRATEGIES);
}

export function buildStrategies() {
  return authRequest(ROUTES.RIPPLETRACE.BUILD_STRATEGIES);
}

export function getStrategy(strategyId) {
  return authRequest(ROUTES.RIPPLETRACE.STRATEGY(strategyId));
}

export function matchStrategies(dropPointId) {
  return authRequest(ROUTES.RIPPLETRACE.MATCH_STRATEGIES(dropPointId));
}

export function getEventDownstream(eventId) {
  return authRequest(ROUTES.RIPPLETRACE.EVENT_DOWNSTREAM(eventId));
}

export function getEventUpstream(eventId) {
  return authRequest(ROUTES.RIPPLETRACE.EVENT_UPSTREAM(eventId));
}
