import { authRequest, taggedRequest, unwrapEnvelope } from "./_core.js";
import { ROUTES } from "./_routes.js";

export const runARMAnalysis = taggedRequest("ARM", (file_path, { complexity, urgency, context } = {}) =>
  authRequest(ROUTES.ARM.ANALYZE, {
    method: "POST",
    body: JSON.stringify({ file_path, complexity, urgency, context }),
  }).then(unwrapEnvelope)
);

export const runARMGenerate = taggedRequest("ARM", (prompt, { original_code, language, generation_type, analysis_id, complexity, urgency } = {}) =>
  authRequest(ROUTES.ARM.GENERATE, {
    method: "POST",
    body: JSON.stringify({ prompt, original_code, language, generation_type, analysis_id, complexity, urgency }),
  }).then(unwrapEnvelope)
);

export const getARMLogs = taggedRequest("ARM", (limit = 20) =>
  authRequest(`${ROUTES.ARM.LOGS}?limit=${limit}`, { method: "GET" }).then(unwrapEnvelope)
);

export const getARMConfig = taggedRequest("ARM", () =>
  authRequest(ROUTES.ARM.CONFIG, { method: "GET" }).then(unwrapEnvelope)
);

export const updateARMConfig = taggedRequest("ARM", (updates) =>
  authRequest(ROUTES.ARM.CONFIG, {
    method: "PUT",
    body: JSON.stringify({ updates }),
  }).then(unwrapEnvelope)
);

export const getARMMetrics = taggedRequest("ARM", (window = 30) =>
  authRequest(`${ROUTES.ARM.METRICS}?window=${window}`, { method: "GET" }).then(unwrapEnvelope)
);

export const getARMConfigSuggestions = taggedRequest("ARM", (window = 30) =>
  authRequest(`${ROUTES.ARM.CONFIG_SUGGESTIONS}?window=${window}`, { method: "GET" }).then(unwrapEnvelope)
);
