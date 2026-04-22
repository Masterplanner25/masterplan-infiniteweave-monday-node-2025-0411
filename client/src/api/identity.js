import { authRequest } from "./_core.js";

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
