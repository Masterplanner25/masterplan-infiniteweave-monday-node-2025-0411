import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function ingestLinkedInManual(payload) {
  return authRequest(ROUTES.ANALYTICS.LINKEDIN_MANUAL, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMasterplanSummary(masterplanId, groupBy = null) {
  const query = groupBy ? `?group_by=${encodeURIComponent(groupBy)}` : "";
  return authRequest(`${ROUTES.ANALYTICS.MASTERPLAN_SUMMARY(masterplanId)}${query}`, {
    method: "GET",
  });
}

export function calculateTwr(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_TWR, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateEngagement(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_ENGAGEMENT, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAiEfficiency(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_AI_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateImpactScore(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_IMPACT_SCORE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateIncomeEfficiency(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_INCOME_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateRevenueScaling(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_REVENUE_SCALING, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateExecutionSpeed(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_EXECUTION_SPEED, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAttentionValue(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_ATTENTION_VALUE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateEngagementRate(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_ENGAGEMENT_RATE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateBusinessGrowth(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_BUSINESS_GROWTH, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateMonetizationEfficiency(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_MONETIZATION_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAiProductivityBoost(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_AI_PRODUCTIVITY_BOOST, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateDecisionEfficiency(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_DECISION_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateLostPotential(payload) {
  return authRequest(ROUTES.ANALYTICS.CALCULATE_LOST_POTENTIAL, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMyScore() {
  return authRequest(ROUTES.ANALYTICS.SCORES_ME, { method: "GET" });
}

export function recalculateScore() {
  return authRequest(ROUTES.ANALYTICS.SCORES_RECALCULATE, { method: "POST" });
}

export function getScoreHistory(limit = 30) {
  return authRequest(`${ROUTES.ANALYTICS.SCORES_HISTORY}?limit=${limit}`, { method: "GET" });
}

export function postScoreFeedback(payload) {
  return authRequest(ROUTES.ANALYTICS.SCORES_FEEDBACK, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getScoreFeedback(limit = 50) {
  return authRequest(`${ROUTES.ANALYTICS.SCORES_FEEDBACK}?limit=${limit}`, { method: "GET" });
}
