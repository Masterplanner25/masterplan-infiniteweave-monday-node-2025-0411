#!/usr/bin/env node
/**
 * Build-time environment validation.
 * Fails the build if required VITE_* variables are missing or wrong.
 * Run via: node scripts/validate-env.js
 */

const REQUIRED_VARS = [
  "VITE_API_BASE_URL",
];

const WARNINGS_IF_MISSING = [
  // Optional but important for observability
];

let hasErrors = false;

for (const varName of REQUIRED_VARS) {
  const value = process.env[varName];
  if (!value || value.trim() === "") {
    console.error(`[build] ERROR: ${varName} is not set.`);
    console.error(
      `  Set ${varName} to the production API URL before building.`,
    );
    console.error(`  Example: VITE_API_BASE_URL=https://api.your-domain.com`);
    hasErrors = true;
    continue;
  }
  if (value.includes("localhost") || value.includes("127.0.0.1")) {
    console.error(
      `[build] ERROR: ${varName}="${value}" points to localhost.`,
    );
    console.error(
      "  This will make the production build unusable outside the build machine.",
    );
    hasErrors = true;
  }
}

for (const varName of WARNINGS_IF_MISSING) {
  const value = process.env[varName];
  if (!value || value.trim() === "") {
    console.warn(`[build] WARNING: ${varName} is not set.`);
  }
}

if (hasErrors) {
  console.error("\n[build] Environment validation FAILED. Aborting build.");
  process.exit(1);
}

console.log("[build] Environment validation passed.");
