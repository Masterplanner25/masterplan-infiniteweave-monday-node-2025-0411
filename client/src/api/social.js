import { authRequest } from "./_core.js";

export function getProfile(username) {
  return authRequest(`/social/profile/${username}`, { method: "GET" });
}

export function upsertProfile(profileData) {
  return authRequest(`/social/profile`, {
    method: "POST",
    body: JSON.stringify(profileData),
  });
}

export function getFeed(limit = 20, trustFilter = null) {
  let path = `/social/feed?limit=${limit}`;
  if (trustFilter) {
    path += `&trust_filter=${trustFilter}`;
  }
  return authRequest(path, { method: "GET" });
}

export function createPost(postData) {
  return authRequest(`/social/post`, {
    method: "POST",
    body: JSON.stringify(postData),
  });
}

export function getSocialAnalytics() {
  return authRequest("/social/analytics", { method: "GET" });
}

export function recordSocialInteraction(postId, action, amount = 1) {
  return authRequest(`/social/posts/${postId}/interact`, {
    method: "POST",
    body: JSON.stringify({ action, amount }),
  });
}
