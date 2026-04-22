/**
 * api.js — Stable public API surface for A.I.N.D.Y. client.
 *
 * This file is the compatibility layer over the modular API modules in ./api/.
 * Import from here to maintain a stable contract; internal modules can be
 * refactored without breaking callers.
 *
 * Implementation lives in ./api/<domain>.js — do not duplicate logic here.
 */

// ── Core utilities ────────────────────────────────────────────────────────────
export {
  API_BASE,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
  buildApiUrl,
  authRequest,
  authRequestExternal,
} from "./api/_core.js";

// ── Auth ──────────────────────────────────────────────────────────────────────
export { loginUser, registerUser, bootIdentity } from "./api/auth.js";

// ── Tasks ─────────────────────────────────────────────────────────────────────
export { getTasks, createTask, completeTask, startTask } from "./api/tasks.js";

// ── Masterplan & Genesis ──────────────────────────────────────────────────────
export {
  startGenesisSession,
  sendGenesisMessage,
  getGenesisSession,
  synthesizeGenesisDraft,
  getGenesisDraft,
  lockMasterPlan,
  auditGenesisDraft,
  listMasterPlans,
  getMasterPlan,
  activateMasterPlan,
  setMasterplanAnchor,
  getMasterplanProjection,
} from "./api/masterplan.js";

// ── ARM ───────────────────────────────────────────────────────────────────────
export {
  runARMAnalysis,
  runARMGenerate,
  getARMLogs,
  getARMConfig,
  updateARMConfig,
  getARMMetrics,
  getARMConfigSuggestions,
} from "./api/arm.js";

// ── Analytics & Scoring ───────────────────────────────────────────────────────
export {
  getMyScore,
  recalculateScore,
  getScoreHistory,
  postScoreFeedback,
  getScoreFeedback,
  ingestLinkedInManual,
  getMasterplanSummary,
  calculateTwr,
  calculateEngagement,
  calculateAiEfficiency,
  calculateImpactScore,
  calculateIncomeEfficiency,
  calculateRevenueScaling,
  calculateExecutionSpeed,
  calculateAttentionValue,
  calculateEngagementRate,
  calculateBusinessGrowth,
  calculateMonetizationEfficiency,
  calculateAiProductivityBoost,
  calculateDecisionEfficiency,
  calculateLostPotential,
} from "./api/analytics.js";

// ── Social ────────────────────────────────────────────────────────────────────
export {
  getProfile,
  upsertProfile,
  getFeed,
  createPost,
  getSocialAnalytics,
  recordSocialInteraction,
} from "./api/social.js";

// ── Search & SEO ──────────────────────────────────────────────────────────────
export {
  runResearch,
  getSearchHistory,
  getSearchHistoryItem,
  deleteSearchHistoryItem,
  runLeadGen,
  analyzeSeo,
  generateMeta,
  suggestSeoImprovements,
} from "./api/search.js";

// ── Memory ────────────────────────────────────────────────────────────────────
export {
  getMemoryNodes,
  recallMemory,
  getMemorySuggestions,
  recordMemoryFeedback,
  getNodePerformance,
  traverseMemory,
  getNodeHistory,
  getFederatedRecall,
  shareMemoryNode,
  getMemoryMetricsDashboard,
} from "./api/memory.js";

// ── Identity ──────────────────────────────────────────────────────────────────
export {
  getIdentityProfile,
  updateIdentityProfile,
  getIdentityEvolution,
  getIdentityContext,
} from "./api/identity.js";

// ── Agent ─────────────────────────────────────────────────────────────────────
export {
  createAgentRun,
  getAgentRuns,
  getAgentRun,
  approveAgentRun,
  rejectAgentRun,
  getAgentRunSteps,
  getAgentTools,
  getAgentTrust,
  updateAgentTrust,
  getAgentSuggestions,
  fetchRunEvents,
  getAgents,
  recallFromAgent,
  getFederatedMemory,
} from "./api/agent.js";

// ── Freelance ─────────────────────────────────────────────────────────────────
export {
  getFreelanceOrders,
  getFreelanceFeedback,
  getFreelanceMetricsLatest,
} from "./api/freelance.js";

// ── RippleTrace ───────────────────────────────────────────────────────────────
export {
  getRippleDropPoints,
  getRipplePings,
  getRecentRippleEvents,
  getRippleTrace,
  getRippleTraceGraph,
} from "./api/rippletrace.js";

// ── Platform (flows, automation, observability, dashboard) ────────────────────
export {
  getDashboardOverview,
  getDashboardHealth,
  getInfluenceGraph,
  getCausalGraph,
  getNarrative,
  getFlowRuns,
  getFlowRun,
  getFlowRunHistory,
  resumeFlowRun,
  getFlowRegistry,
  getAutomationLogs,
  getAutomationLog,
  replayAutomationLog,
  getSchedulerStatus,
  getObservabilityRequests,
  getObservabilityDashboard,
} from "./api/platform.js";

// ── Endpoint constants ────────────────────────────────────────────────────────
// Canonical path strings for key API endpoints. Declared here so callers and
// tests have a single source of truth without importing individual modules.
export const ENDPOINTS = {
  SCORES_ME: "/scores/me",
  SCORES_FEEDBACK: "/scores/feedback",
  AGENT_SUGGESTIONS: "/agent/suggestions",
};
