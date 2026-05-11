import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function runResearch(query, summary) {
  return authRequest(ROUTES.SEARCH.RESEARCH_QUERY, {
    method: "POST",
    body: JSON.stringify({ query, summary }),
  });
}

export function getSearchHistory(searchType = null, limit = 25) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (searchType) params.append("search_type", searchType);
  return authRequest(`${ROUTES.SEARCH.HISTORY}?${params.toString()}`, { method: "GET" });
}

export function getSearchHistoryItem(historyId) {
  return authRequest(ROUTES.SEARCH.HISTORY_ITEM(historyId), { method: "GET" });
}

export function deleteSearchHistoryItem(historyId) {
  return authRequest(ROUTES.SEARCH.HISTORY_ITEM(historyId), { method: "DELETE" });
}

export function runLeadGen(query) {
  return authRequest(`${ROUTES.SEARCH.LEAD_GEN}?query=${encodeURIComponent(query)}`, {
    method: "POST",
  });
}

export function analyzeSeo(content) {
  return authRequest(ROUTES.SEARCH.ANALYZE_SEO, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function generateMeta(content) {
  return authRequest(ROUTES.SEARCH.GENERATE_META, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function suggestSeoImprovements(content) {
  return authRequest(ROUTES.SEARCH.SUGGEST_IMPROVEMENTS, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}
