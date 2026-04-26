import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getProfile(username) {
  return authRequest(ROUTES.SOCIAL.PROFILE_BY_USERNAME(username), { method: "GET" });
}

export function upsertProfile(profileData) {
  return authRequest(ROUTES.SOCIAL.PROFILE, {
    method: "POST",
    body: JSON.stringify(profileData),
  });
}

export function getFeed(limit = 20, trustFilter = null) {
  let path = `${ROUTES.SOCIAL.FEED}?limit=${limit}`;
  if (trustFilter) {
    path += `&trust_filter=${trustFilter}`;
  }
  return authRequest(path, { method: "GET" });
}

export function createPost(postData) {
  return authRequest(ROUTES.SOCIAL.POST, {
    method: "POST",
    body: JSON.stringify(postData),
  });
}

export function getSocialAnalytics() {
  return authRequest(ROUTES.SOCIAL.ANALYTICS, { method: "GET" });
}

export function recordSocialInteraction(postId, action, amount = 1) {
  return authRequest(ROUTES.SOCIAL.INTERACT(postId), {
    method: "POST",
    body: JSON.stringify({ action, amount }),
  });
}
