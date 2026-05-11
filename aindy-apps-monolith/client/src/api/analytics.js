import { authRequest, taggedRequest, unwrapEnvelope } from "./_core.js";
import { ROUTES } from "./_routes.js";

export const ingestLinkedInManual = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.LINKEDIN_MANUAL, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const getMasterplanSummary = taggedRequest("analytics", (masterplanId, groupBy = null) => {
  const query = groupBy ? `?group_by=${encodeURIComponent(groupBy)}` : "";
  return authRequest(`${ROUTES.ANALYTICS.MASTERPLAN_SUMMARY(masterplanId)}${query}`, {
    method: "GET",
  }).then(unwrapEnvelope);
});

export const calculateTwr = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_TWR, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateEngagement = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_ENGAGEMENT, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateAiEfficiency = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_AI_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateImpactScore = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_IMPACT_SCORE, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateIncomeEfficiency = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_INCOME_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateRevenueScaling = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_REVENUE_SCALING, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateExecutionSpeed = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_EXECUTION_SPEED, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateAttentionValue = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_ATTENTION_VALUE, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateEngagementRate = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_ENGAGEMENT_RATE, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateBusinessGrowth = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_BUSINESS_GROWTH, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateMonetizationEfficiency = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_MONETIZATION_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateAiProductivityBoost = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_AI_PRODUCTIVITY_BOOST, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateDecisionEfficiency = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_DECISION_EFFICIENCY, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const calculateLostPotential = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.CALCULATE_LOST_POTENTIAL, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const getMyScore = taggedRequest("analytics", () =>
  authRequest(ROUTES.ANALYTICS.SCORES_ME, { method: "GET" }).then(unwrapEnvelope)
);

export const recalculateScore = taggedRequest("analytics", () =>
  authRequest(ROUTES.ANALYTICS.SCORES_RECALCULATE, { method: "POST" }).then(unwrapEnvelope)
);

export const getScoreHistory = taggedRequest("analytics", (limit = 30) =>
  authRequest(`${ROUTES.ANALYTICS.SCORES_HISTORY}?limit=${limit}`, { method: "GET" }).then(unwrapEnvelope)
);

export const postScoreFeedback = taggedRequest("analytics", (payload) =>
  authRequest(ROUTES.ANALYTICS.SCORES_FEEDBACK, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(unwrapEnvelope)
);

export const getScoreFeedback = taggedRequest("analytics", (limit = 50) =>
  authRequest(`${ROUTES.ANALYTICS.SCORES_FEEDBACK}?limit=${limit}`, { method: "GET" }).then(unwrapEnvelope)
);
