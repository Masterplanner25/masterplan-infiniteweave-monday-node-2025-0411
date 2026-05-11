import { getStoredToken, request } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function loginUser(credentials) {
  return request(ROUTES.AUTH.LOGIN, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function registerUser(credentials) {
  return request(ROUTES.AUTH.REGISTER, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function bootIdentity(token = getStoredToken()) {
  return request(ROUTES.IDENTITY.BOOT, {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}
