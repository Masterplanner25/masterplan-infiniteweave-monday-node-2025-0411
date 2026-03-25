// client/src/api.js
const API_BASE = "http://127.0.0.1:8000"; // your FastAPI backend

// ✅ Helper function to handle all requests consistently
async function request(path, opts = {}) {
  const url = `${API_BASE}${path}`; // FIXED: Changed BASE_URL to API_BASE

  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });

  // Handle API errors (404, 500, etc.)
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error (${res.status}): ${errText}`);
  }

  // Handle response parsing
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/* --- Auth helper (injects Bearer token from localStorage) --- */
function authRequest(path, opts = {}) {
  const token = localStorage.getItem("aindy_token");
  return request(path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

/* --- Auth helper for absolute URLs (used by legacy gateway endpoints) --- */
async function requestAbsolute(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error (${res.status}): ${errText}`);
  }

  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function authRequestExternal(url, opts = {}) {
  const token = localStorage.getItem("aindy_token");
  return requestAbsolute(url, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

/* --- Research Endpoints --- */
export function runResearch(query, summary) {
  return authRequest(`/research/query`, {
    method: "POST",
    body: JSON.stringify({ query, summary }),
  });
}

/* --- ARM Endpoints --- */
export function runARMAnalysis(file_path, { complexity, urgency, context } = {}) {
  return authRequest(`/arm/analyze`, {
    method: "POST",
    body: JSON.stringify({ file_path, complexity, urgency, context }),
  });
}

export function runARMGenerate(prompt, { original_code, language, generation_type, analysis_id, complexity, urgency } = {}) {
  return authRequest(`/arm/generate`, {
    method: "POST",
    body: JSON.stringify({ prompt, original_code, language, generation_type, analysis_id, complexity, urgency }),
  });
}

export function getARMLogs(limit = 20) {
  return authRequest(`/arm/logs?limit=${limit}`, { method: "GET" });
}

export function getARMConfig() {
  return authRequest(`/arm/config`, { method: "GET" });
}

export function updateARMConfig(updates) {
  return authRequest(`/arm/config`, {
    method: "PUT",
    body: JSON.stringify({ updates }),
  });
}

export function getARMMetrics(window = 30) {
  return authRequest(`/arm/metrics?window=${window}`, { method: "GET" });
}

export function getARMConfigSuggestions(window = 30) {
  return authRequest(`/arm/config/suggest?window=${window}`, { method: "GET" });
}

export function runLeadGen(query) {
  return authRequest(`/leadgen/?query=${encodeURIComponent(query)}`, {
    method: "POST",
  });
}

/* --- Social / Network Layer Endpoints --- */

/**
 * Fetch a public profile by username
 */
export function getProfile(username) {
  return authRequest(`/social/profile/${username}`, { method: "GET" });
}

/**
 * Create or Update the current user's profile
 * @param {Object} profileData - { username, tagline, bio, tags, etc. }
 */
export function upsertProfile(profileData) {
  return authRequest(`/social/profile`, {
    method: "POST",
    body: JSON.stringify(profileData),
  });
}

/**
 * Fetch the main activity feed
 * @param {number} limit - Number of posts to fetch (default 20)
 * @param {string} trustFilter - Optional: "inner", "collab", "observer"
 */
export function getFeed(limit = 20, trustFilter = null) {
  let path = `/social/feed?limit=${limit}`;
  if (trustFilter) {
    path += `&trust_filter=${trustFilter}`;
  }
  return authRequest(path, { method: "GET" });
}

/**
 * Create a new social post
 * @param {Object} postData - { author_id, author_username, content, trust_tier_required, tags }
 */
export function createPost(postData) {
  return authRequest(`/social/post`, {
    method: "POST",
    body: JSON.stringify(postData),
  });
}

/* --- Execution Engine / Task Endpoints --- */

export function getTasks() {
  return authRequest(`/tasks/list`, { method: "GET" });
}

export function createTask(taskData) {
  // taskData = { name, category, priority }
  return authRequest(`/tasks/create`, {
    method: "POST",
    body: JSON.stringify(taskData),
  });
}

export function completeTask(taskName) {
  return authRequest(`/tasks/complete`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}

export function startTask(taskName) {
  return authRequest(`/tasks/start`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}

/* --- Genesis Endpoints --- */

export function startGenesisSession() {
  return authRequest("/genesis/session", { method: "POST" });
}

export function sendGenesisMessage(sessionId, message) {
  return authRequest("/genesis/message", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export function getGenesisSession(sessionId) {
  return authRequest(`/genesis/session/${sessionId}`, { method: "GET" });
}

export function synthesizeGenesisDraft(sessionId) {
  return authRequest("/genesis/synthesize", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function getGenesisDraft(sessionId) {
  return authRequest(`/genesis/draft/${sessionId}`, { method: "GET" });
}

export function lockMasterPlan(sessionId, draft) {
  return authRequest("/genesis/lock", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, draft }),
  });
}

export function auditGenesisDraft(sessionId) {
  return authRequest("/genesis/audit", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

/* --- MasterPlan Endpoints --- */

export function listMasterPlans() {
  return authRequest("/masterplans/", { method: "GET" });
}

export function getMasterPlan(planId) {
  return authRequest(`/masterplans/${planId}`, { method: "GET" });
}

export function activateMasterPlan(planId) {
  return authRequest(`/masterplans/${planId}/activate`, { method: "POST" });
}

export function setMasterplanAnchor(planId, anchorData) {
  return authRequest(`/masterplans/${planId}/anchor`, {
    method: "PUT",
    body: JSON.stringify(anchorData),
  });
}

export function getMasterplanProjection(planId) {
  return authRequest(`/masterplans/${planId}/projection`, { method: "GET" });
}

/* --- Dashboard Endpoints --- */
export function getDashboardOverview() {
  return authRequest("/dashboard/overview", { method: "GET" });
}

export function getDashboardHealth() {
  return authRequest("/dashboard/health", { method: "GET" });
}

export function getInfluenceGraph() {
  return authRequest("/influence_graph", { method: "GET" });
}

export function getCausalGraph() {
  return authRequest("/causal_graph", { method: "GET" });
}

export function getNarrative(dropPointId) {
  return authRequest(`/narrative/${dropPointId}`, { method: "GET" });
}

/* --- Analytics Endpoints --- */
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

/* --- Execution Metrics Endpoints --- */
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

/* --- SEO Tool Endpoints --- */
export function analyzeSeo(content) {
  return authRequest("/analyze_seo/", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function generateMeta(content) {
  return authRequest("/generate_meta/", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function suggestSeoImprovements(content) {
  return authRequest("/suggest_improvements/", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/* --- Memory Browser Endpoints --- */
export function getMemoryNodes(tags = [], limit = 20) {
  const tagParam = tags.length ? `&tags=${tags.join(",")}` : "";
  return authRequest(`/memory/nodes?limit=${limit}${tagParam}`, { method: "GET" });
}

export function recallMemory(query, tags = [], limit = 5, expandResults = false) {
  return authRequest("/memory/recall/v3", {
    method: "POST",
    body: JSON.stringify({ query, tags, limit, expand_results: expandResults }),
  });
}

export function getMemorySuggestions(query, tags = [], limit = 3) {
  return authRequest("/memory/suggest", {
    method: "POST",
    body: JSON.stringify({ query, tags, limit }),
  });
}

export function recordMemoryFeedback(nodeId, outcome, context = "") {
  return authRequest(`/memory/nodes/${nodeId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ outcome, context }),
  });
}

export function getNodePerformance(nodeId) {
  return authRequest(`/memory/nodes/${nodeId}/performance`, { method: "GET" });
}

export function traverseMemory(nodeId, maxDepth = 3) {
  return authRequest(`/memory/nodes/${nodeId}/traverse?max_depth=${maxDepth}`, { method: "GET" });
}

export function getNodeHistory(nodeId, limit = 10) {
  return authRequest(`/memory/nodes/${nodeId}/history?limit=${limit}`, { method: "GET" });
}

export function getFederatedRecall(query, tags = [], agentNamespaces = null, limit = 5) {
  return authRequest("/memory/federated/recall", {
    method: "POST",
    body: JSON.stringify({ query, tags, agent_namespaces: agentNamespaces, limit }),
  });
}

export function shareMemoryNode(nodeId) {
  return authRequest(`/memory/nodes/${nodeId}/share`, { method: "POST" });
}

/* --- Identity Endpoints --- */
export function getIdentityProfile() {
  return authRequest("/identity/", { method: "GET" });
}

export function updateIdentityProfile(updates) {
  return authRequest("/identity/", {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export function getIdentityEvolution() {
  return authRequest("/identity/evolution", { method: "GET" });
}

export function getIdentityContext() {
  return authRequest("/identity/context", { method: "GET" });
}

/* --- Agent Registry Endpoints --- */
export function getAgents() {
  return authRequest("/memory/agents", { method: "GET" });
}

export function recallFromAgent(namespace, query = "", limit = 5) {
  return authRequest(
    `/memory/agents/${namespace}/recall?query=${encodeURIComponent(query)}&limit=${limit}`,
    { method: "GET" }
  );
}

export function getFederatedMemory(query, namespaces = null, limit = 5) {
  return authRequest("/memory/federated/recall", {
    method: "POST",
    body: JSON.stringify({ query, agent_namespaces: namespaces, limit }),
  });
}

/* --- Freelance Endpoints --- */
export function getFreelanceOrders() {
  return authRequest("/freelance/orders", { method: "GET" });
}

export function getFreelanceFeedback() {
  return authRequest("/freelance/feedback", { method: "GET" });
}

export function getFreelanceMetricsLatest() {
  return authRequest("/freelance/metrics/latest", { method: "GET" });
}

// ── Flow Engine ──────────────────────────────────────────────────────────────

export function getFlowRuns(status = null, workflowType = null, limit = 20) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (workflowType) params.append("workflow_type", workflowType);
  params.append("limit", limit);
  return authRequest(`/flows/runs?${params.toString()}`, { method: "GET" });
}

export function getFlowRun(runId) {
  return authRequest(`/flows/runs/${runId}`, { method: "GET" });
}

export function getFlowRunHistory(runId) {
  return authRequest(`/flows/runs/${runId}/history`, { method: "GET" });
}

export function resumeFlowRun(runId, eventType, payload = {}) {
  return authRequest(`/flows/runs/${runId}/resume`, {
    method: "POST",
    body: JSON.stringify({ event_type: eventType, payload }),
  });
}

export function getFlowRegistry() {
  return authRequest("/flows/registry", { method: "GET" });
}

// ── Automation Logs ──────────────────────────────────────────────────────────

export function getAutomationLogs(status = null, source = null, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (source) params.append("source", source);
  params.append("limit", limit);
  return authRequest(`/automation/logs?${params.toString()}`, { method: "GET" });
}

export function getAutomationLog(logId) {
  return authRequest(`/automation/logs/${logId}`, { method: "GET" });
}

export function replayAutomationLog(logId) {
  return authRequest(`/automation/logs/${logId}/replay`, { method: "POST" });
}

export function getSchedulerStatus() {
  return authRequest("/automation/scheduler/status", { method: "GET" });
}

// ── Infinity Score ────────────────────────────────────────────────────────────

export function getMyScore() {
  return authRequest("/scores/me", { method: "GET" });
}

export function recalculateScore() {
  return authRequest("/scores/me/recalculate", { method: "POST" });
}

export function getScoreHistory(limit = 30) {
  return authRequest(`/scores/me/history?limit=${limit}`, { method: "GET" });
}

// ── Agent ─────────────────────────────────────────────────────────────────────

export function createAgentRun(payload) {
  return authRequest("/agent/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentRuns(status = null, limit = 20) {
  const params = new URLSearchParams({ limit });
  if (status) params.append("status", status);
  return authRequest(`/agent/runs?${params.toString()}`, { method: "GET" });
}

export function getAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}`, { method: "GET" });
}

export function approveAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}/approve`, { method: "POST" });
}

export function rejectAgentRun(runId) {
  return authRequest(`/agent/runs/${runId}/reject`, { method: "POST" });
}

export function getAgentRunSteps(runId) {
  return authRequest(`/agent/runs/${runId}/steps`, { method: "GET" });
}

export function getAgentTools() {
  return authRequest("/agent/tools", { method: "GET" });
}

export function getAgentTrust() {
  return authRequest("/agent/trust", { method: "GET" });
}

export function updateAgentTrust(payload) {
  return authRequest("/agent/trust", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAgentSuggestions() {
  return authRequest("/agent/suggestions", { method: "GET" });
}

export async function fetchRunEvents(runId) {
  return authRequest(`/agent/runs/${runId}/events`);
}
