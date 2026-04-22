import { getStoredToken, request } from "./_core.js";

export function loginUser(credentials) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function registerUser(credentials) {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function bootIdentity(token = getStoredToken()) {
  return request("/identity/boot", {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}
