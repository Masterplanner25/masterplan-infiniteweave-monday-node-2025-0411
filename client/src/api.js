/**
 * api.js — Stable public compatibility API surface for the client.
 *
 * Prefer the explicit category modules for new code:
 * - ./api/product.js
 * - ./api/operator.js
 * - ./api/legacy.js
 *
 * This file remains as a flat compatibility barrel for older imports.
 */

export * from "./api/index.js";

export const ENDPOINTS = {
  SCORES_ME: "/scores/me",
  SCORES_FEEDBACK: "/scores/feedback",
  AGENT_SUGGESTIONS: "/agent/suggestions",
};
