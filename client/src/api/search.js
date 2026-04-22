import { authRequest } from "./_core.js";

export function runResearch(query, summary) {
  return authRequest(`/research/query`, {
    method: "POST",
    body: JSON.stringify({ query, summary }),
  });
}

export function getSearchHistory(searchType = null, limit = 25) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (searchType) params.append("search_type", searchType);
  return authRequest(`/search/history?${params.toString()}`, { method: "GET" });
}

export function getSearchHistoryItem(historyId) {
  return authRequest(`/search/history/${historyId}`, { method: "GET" });
}

export function deleteSearchHistoryItem(historyId) {
  return authRequest(`/search/history/${historyId}`, { method: "DELETE" });
}

export function runLeadGen(query) {
  return authRequest(`/leadgen/?query=${encodeURIComponent(query)}`, {
    method: "POST",
  });
}

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
