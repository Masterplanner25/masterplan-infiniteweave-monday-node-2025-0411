import { describe, expect, it } from "vitest";

import { ROUTES } from "../api/_routes.js";

describe("API route registry", () => {
  it("freezes the top-level registry and nested domain maps", () => {
    expect(Object.isFrozen(ROUTES)).toBe(true);

    for (const paths of Object.values(ROUTES)) {
      expect(Object.isFrozen(paths)).toBe(true);
    }

    expect(() => {
      ROUTES.AUTH = {};
    }).toThrow(TypeError);
  });

  it("uses only strings or functions for route entries", () => {
    for (const [domain, paths] of Object.entries(ROUTES)) {
      for (const [key, value] of Object.entries(paths)) {
        expect(
          typeof value === "string" || typeof value === "function",
          `ROUTES.${domain}.${key} must be string or function`,
        ).toBe(true);
      }
    }
  });

  it("builds representative static and dynamic paths correctly", () => {
    expect(ROUTES.OPERATOR.FLOW_RUN("abc-123")).toBe("/flows/runs/abc-123");
    expect(ROUTES.ARM.ANALYZE).toBe("/arm/analyze");
    expect(ROUTES.AGENT.EVENTS("run-7")).toBe("/agent/runs/run-7/events");
    expect(ROUTES.MASTERPLAN.PLAN_ANCHOR("plan-9")).toBe("/masterplans/plan-9/anchor");
    expect(ROUTES.RIPPLETRACE.CAUSAL_CHAIN("drop 1")).toBe("/rippletrace/causal/chain/drop%201");
    expect(ROUTES.PLATFORM.VERSION).toBe("/api/version");
  });

  it("imports every API module without error", async () => {
    const modules = await Promise.all([
      import("../api/auth.js"),
      import("../api/tasks.js"),
      import("../api/agent.js"),
      import("../api/analytics.js"),
      import("../api/arm.js"),
      import("../api/freelance.js"),
      import("../api/identity.js"),
      import("../api/masterplan.js"),
      import("../api/memory.js"),
      import("../api/search.js"),
      import("../api/social.js"),
      import("../api/rippletrace.js"),
      import("../api/operator.js"),
      import("../api/product.js"),
      import("../api/platform.js"),
    ]);

    modules.forEach((moduleExports) => {
      expect(moduleExports).toBeDefined();
    });
  });
});
