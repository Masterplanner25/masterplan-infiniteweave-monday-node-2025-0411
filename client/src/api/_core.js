import { safeMap } from "../utils/safe";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_STORAGE_KEY = "token";
const LEGACY_TOKEN_STORAGE_KEY = "aindy_token";
const NORMALIZED_ARRAY_KEYS = new Set([
  "agents",
  "allowed_auto_grant_tools",
  "allowed_capabilities",
  "analyses",
  "drop_points",
  "end",
  "error_rate_series",
  "events",
  "feedback",
  "fields",
  "findings",
  "flows",
  "generations",
  "granted_tools",
  "history",
  "items",
  "jobs",
  "logs",
  "memories",
  "nodes",
  "plans",
  "pings",
  "recent",
  "recent_authors",
  "recent_changes",
  "recent_errors",
  "recent_ripples",
  "results",
  "runs",
  "steps",
  "strategies",
  "suggestions",
  "tags",
  "timeline",
  "tools",
]);

function normalizeArrayFields(value) {
  if (Array.isArray(value)) {
    return safeMap(value, (item) => normalizeArrayFields(item));
  }

  if (!value || typeof value !== "object") {
    return value;
  }

  const normalized = {};
  for (const [key, entry] of Object.entries(value)) {
    if (NORMALIZED_ARRAY_KEYS.has(key)) {
      normalized[key] = Array.isArray(entry) ? safeMap(entry, (item) => normalizeArrayFields(item)) : [];
      continue;
    }
    normalized[key] = normalizeArrayFields(entry);
  }
  return normalized;
}

export function getStoredToken() {
  return (
    localStorage.getItem(TOKEN_STORAGE_KEY) ||
    localStorage.getItem(LEGACY_TOKEN_STORAGE_KEY) ||
    ""
  );
}

export function setStoredToken(token) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(LEGACY_TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
}

export function buildApiUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return API_BASE ? `${API_BASE}${path}` : path;
}

async function request(path, opts = {}) {
  const url = buildApiUrl(path);
  const token = getStoredToken();

  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error (${res.status}): ${errText}`);
  }

  const text = await res.text();
  try {
    return normalizeArrayFields(JSON.parse(text));
  } catch {
    return text;
  }
}

function authRequest(path, opts = {}) {
  return request(path, {
    ...opts,
  });
}

async function requestAbsolute(url, opts = {}) {
  const token = getStoredToken();
  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error (${res.status}): ${errText}`);
  }

  const text = await res.text();
  try {
    return normalizeArrayFields(JSON.parse(text));
  } catch {
    return text;
  }
}

export function authRequestExternal(url, opts = {}) {
  return requestAbsolute(url, {
    ...opts,
  });
}

export {
  API_BASE,
  authRequest,
  request,
  requestAbsolute,
};
