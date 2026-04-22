import { authRequest } from "./_core.js";

export function ingestLinkedInManual(payload) {
  return authRequest("/analytics/linkedin/manual", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMasterplanSummary(masterplanId, groupBy = null) {
  const query = groupBy ? `?group_by=${encodeURIComponent(groupBy)}` : "";
  return authRequest(`/analytics/masterplan/${masterplanId}/summary${query}`, {
    method: "GET",
  });
}

export function calculateTwr(payload) {
  return authRequest("/calculate_twr", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateEngagement(payload) {
  return authRequest("/calculate_engagement", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAiEfficiency(payload) {
  return authRequest("/calculate_ai_efficiency", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateImpactScore(payload) {
  return authRequest("/calculate_impact_score", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateIncomeEfficiency(payload) {
  return authRequest("/income_efficiency", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateRevenueScaling(payload) {
  return authRequest("/revenue_scaling", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateExecutionSpeed(payload) {
  return authRequest("/execution_speed", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAttentionValue(payload) {
  return authRequest("/attention_value", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateEngagementRate(payload) {
  return authRequest("/engagement_rate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateBusinessGrowth(payload) {
  return authRequest("/business_growth", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateMonetizationEfficiency(payload) {
  return authRequest("/monetization_efficiency", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateAiProductivityBoost(payload) {
  return authRequest("/ai_productivity_boost", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateDecisionEfficiency(payload) {
  return authRequest("/decision_efficiency", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateLostPotential(payload) {
  return authRequest("/lost_potential", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMyScore() {
  return authRequest("/scores/me", { method: "GET" });
}

export function recalculateScore() {
  return authRequest("/scores/me/recalculate", { method: "POST" });
}

export function getScoreHistory(limit = 30) {
  return authRequest(`/scores/me/history?limit=${limit}`, { method: "GET" });
}

export function postScoreFeedback(payload) {
  return authRequest("/scores/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getScoreFeedback(limit = 50) {
  return authRequest(`/scores/feedback?limit=${limit}`, { method: "GET" });
}
