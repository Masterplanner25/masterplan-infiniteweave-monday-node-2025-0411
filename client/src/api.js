/**
 * api.js - Stable public compatibility API surface for the client.
 *
 * Prefer the explicit category modules for new code:
 * - ./api/product.js
 * - ./api/operator.js
 * - ./api/legacy.js
 *
 * This file remains as a flat compatibility barrel for older imports and
 * contract tests that still inspect `client/src/api.js` directly.
 */

import * as productApi from "./api/product.js";
import * as operatorApi from "./api/operator.js";
import * as legacyApi from "./api/legacy.js";

export * from "./api/index.js";

export { productApi, operatorApi, legacyApi };

export const ENDPOINTS = {
  GET_FLOW_RUNS: "/flow/runs",
  SCORES_ME: "/scores/me",
  SCORES_FEEDBACK: "/scores/feedback",
  AGENT_SUGGESTIONS: "/agent/suggestions",
};

// Flow/operator compatibility
export function getFlowRuns(status = null, workflowType = null, limit = 20) {
  return operatorApi.getFlowRuns(status, workflowType, limit);
}

export function getFlowRun(runId) {
  return operatorApi.getFlowRun(runId);
}

export function getFlowRunHistory(runId) {
  return operatorApi.getFlowRunHistory(runId);
}

export function resumeFlowRun(runId, eventType, payload = {}) {
  return operatorApi.resumeFlowRun(runId, eventType, payload);
}

export function getFlowRegistry() {
  return operatorApi.getFlowRegistry();
}

export function getAutomationLogs(status = null, source = null, limit = 50) {
  return operatorApi.getAutomationLogs(status, source, limit);
}

export function getAutomationLog(logId) {
  return operatorApi.getAutomationLog(logId);
}

export function replayAutomationLog(logId) {
  return operatorApi.replayAutomationLog(logId);
}

export function getSchedulerStatus() {
  return operatorApi.getSchedulerStatus();
}

// Score/product compatibility
export function getMyScore() {
  return productApi.getMyScore();
}

export function recalculateScore() {
  return productApi.recalculateScore();
}

export function getScoreHistory(limit = 30) {
  return productApi.getScoreHistory(limit);
}

export function postScoreFeedback(payload) {
  return productApi.postScoreFeedback(payload);
}

export function getScoreFeedback(limit = 50) {
  return productApi.getScoreFeedback(limit);
}

// Agent/product compatibility
export function createAgentRun(payload) {
  return productApi.createAgentRun(payload);
}

export function getAgentRuns(status = null, limit = 20) {
  return productApi.getAgentRuns(status, limit);
}

export function approveAgentRun(runId) {
  return productApi.approveAgentRun(runId);
}

export function rejectAgentRun(runId) {
  return productApi.rejectAgentRun(runId);
}

export function getAgentTools() {
  return productApi.getAgentTools();
}

export function getAgentTrust() {
  return productApi.getAgentTrust();
}

export function updateAgentTrust(payload) {
  return productApi.updateAgentTrust(payload);
}

export function getAgentSuggestions() {
  return productApi.getAgentSuggestions();
}
