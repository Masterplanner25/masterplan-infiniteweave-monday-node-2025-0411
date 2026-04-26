import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function runARMAnalysis(file_path, { complexity, urgency, context } = {}) {
  return authRequest(ROUTES.ARM.ANALYZE, {
    method: "POST",
    body: JSON.stringify({ file_path, complexity, urgency, context }),
  });
}

export function runARMGenerate(prompt, { original_code, language, generation_type, analysis_id, complexity, urgency } = {}) {
  return authRequest(ROUTES.ARM.GENERATE, {
    method: "POST",
    body: JSON.stringify({ prompt, original_code, language, generation_type, analysis_id, complexity, urgency }),
  });
}

export function getARMLogs(limit = 20) {
  return authRequest(`${ROUTES.ARM.LOGS}?limit=${limit}`, { method: "GET" });
}

export function getARMConfig() {
  return authRequest(ROUTES.ARM.CONFIG, { method: "GET" });
}

export function updateARMConfig(updates) {
  return authRequest(ROUTES.ARM.CONFIG, {
    method: "PUT",
    body: JSON.stringify({ updates }),
  });
}

export function getARMMetrics(window = 30) {
  return authRequest(`${ROUTES.ARM.METRICS}?window=${window}`, { method: "GET" });
}

export function getARMConfigSuggestions(window = 30) {
  return authRequest(`${ROUTES.ARM.CONFIG_SUGGESTIONS}?window=${window}`, { method: "GET" });
}
