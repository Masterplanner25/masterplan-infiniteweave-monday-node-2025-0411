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
