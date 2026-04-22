import { authRequest } from "./_core.js";

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
