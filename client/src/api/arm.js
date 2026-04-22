import { authRequest } from "./_core.js";

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
