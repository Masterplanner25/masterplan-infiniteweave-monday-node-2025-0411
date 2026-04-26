import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getIdentityProfile() {
  return authRequest(ROUTES.IDENTITY.PROFILE, { method: "GET" });
}

export function updateIdentityProfile(updates) {
  return authRequest(ROUTES.IDENTITY.PROFILE, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export function getIdentityEvolution() {
  return authRequest(ROUTES.IDENTITY.EVOLUTION, { method: "GET" });
}

export function getIdentityContext() {
  return authRequest(ROUTES.IDENTITY.CONTEXT, { method: "GET" });
}
