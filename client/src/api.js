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

/* --- Research Endpoints --- */
export function runResearch(query, summary) {
  // Refactored to use the shared 'request' helper
  return request(`/research/query`, {
    method: "POST",
    body: JSON.stringify({ query, summary }),
  });
}

/* --- ARM Endpoints --- */
export function runARMAnalysis(file_path) {
  return request(`/arm/analyze`, {
    method: "POST",
    body: JSON.stringify({ file_path }),
  });
}

export function runARMGenerate(file_path, instructions) {
  return request(`/arm/generate`, {
    method: "POST",
    body: JSON.stringify({ file_path, instructions }),
  });
}

export function getARMLogs() {
  return request(`/arm/logs`, { method: "GET" });
}

export function getARMConfig() {
  return request(`/arm/config`, { method: "GET" });
}

export function updateARMConfig(parameter, value) {
  return request(`/arm/config`, {
    method: "PUT",
    body: JSON.stringify({ parameter, value }),
  });
}

export async function runLeadGen(query) {
  const response = await fetch(`${API_BASE}/leadgen/?query=${encodeURIComponent(query)}`, {
    method: "POST"
  });

  if (!response.ok) throw new Error("LeadGen API error");

  return response.json();
}

/* --- Social / Network Layer Endpoints --- */

/**
 * Fetch a public profile by username
 */
export function getProfile(username) {
  return request(`/social/profile/${username}`, { method: "GET" });
}

/**
 * Create or Update the current user's profile
 * @param {Object} profileData - { username, tagline, bio, tags, etc. }
 */
export function upsertProfile(profileData) {
  return request(`/social/profile`, {
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
  return request(path, { method: "GET" });
}

/**
 * Create a new social post
 * @param {Object} postData - { author_id, author_username, content, trust_tier_required, tags }
 */
export function createPost(postData) {
  return request(`/social/post`, {
    method: "POST",
    body: JSON.stringify(postData),
  });
}

/* --- Execution Engine / Task Endpoints --- */

export function getTasks() {
  return request(`/tasks/list`, { method: "GET" });
}

export function createTask(taskData) {
  // taskData = { name, category, priority }
  return request(`/tasks/create`, {
    method: "POST",
    body: JSON.stringify(taskData),
  });
}

export function completeTask(taskName) {
  return request(`/tasks/complete`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}

export function startTask(taskName) {
  return request(`/tasks/start`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}