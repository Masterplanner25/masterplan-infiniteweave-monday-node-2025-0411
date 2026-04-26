import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getFreelanceOrders() {
  return authRequest(ROUTES.FREELANCE.ORDERS, { method: "GET" });
}

export function getFreelanceFeedback() {
  return authRequest(ROUTES.FREELANCE.FEEDBACK, { method: "GET" });
}

export function getFreelanceMetricsLatest() {
  return authRequest(ROUTES.FREELANCE.METRICS_LATEST, { method: "GET" });
}
