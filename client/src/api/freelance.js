import { authRequest } from "./_core.js";

export function getFreelanceOrders() {
  return authRequest("/freelance/orders", { method: "GET" });
}

export function getFreelanceFeedback() {
  return authRequest("/freelance/feedback", { method: "GET" });
}

export function getFreelanceMetricsLatest() {
  return authRequest("/freelance/metrics/latest", { method: "GET" });
}
