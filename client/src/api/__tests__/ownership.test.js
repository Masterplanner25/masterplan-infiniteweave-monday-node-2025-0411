import { readFileSync } from "node:fs";

import { describe, expect, it, beforeEach, vi } from "vitest";

vi.mock("../_core.js", () => ({
  authRequest: vi.fn(),
}));

import { authRequest } from "../_core.js";
import * as operatorApi from "../operator.js";
import * as legacyApi from "../legacy.js";
import * as platformApi from "../platform.js";
import * as barrelApi from "../../api.js";

describe("client API ownership boundaries", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("routes operator APIs through operator-owned endpoints", () => {
    operatorApi.getFlowRuns("waiting", "agent", 10);
    operatorApi.getSchedulerStatus();
    operatorApi.getObservabilityDashboard(12);

    expect(authRequest).toHaveBeenNthCalledWith(
      1,
      "/flows/runs?status=waiting&workflow_type=agent&limit=10",
      { method: "GET" },
    );
    expect(authRequest).toHaveBeenNthCalledWith(
      2,
      "/automation/scheduler/status",
      { method: "GET" },
    );
    expect(authRequest).toHaveBeenNthCalledWith(
      3,
      "/observability/dashboard?window_hours=12",
      { method: "GET" },
    );
  });

  it("routes legacy or mixed APIs through the legacy module", () => {
    legacyApi.getDashboardOverview();
    legacyApi.getDashboardHealth();
    legacyApi.getNarrative("drop-1");

    expect(authRequest).toHaveBeenNthCalledWith(1, "/dashboard/overview", { method: "GET" });
    expect(authRequest).toHaveBeenNthCalledWith(2, "/dashboard/health", { method: "GET" });
    expect(authRequest).toHaveBeenNthCalledWith(3, "/narrative/drop-1", { method: "GET" });
  });

  it("keeps platform.js scoped to operator APIs only", () => {
    expect(platformApi.getFlowRuns).toBeTypeOf("function");
    expect(platformApi.getObservabilityDashboard).toBeTypeOf("function");
    expect("getDashboardOverview" in platformApi).toBe(false);
    expect("getNarrative" in platformApi).toBe(false);
  });

  it("preserves backward-compatible flat exports while exposing explicit categories", () => {
    expect(barrelApi.getMyScore).toBeTypeOf("function");
    expect(barrelApi.getFlowRuns).toBeTypeOf("function");
    expect(barrelApi.getDashboardOverview).toBeTypeOf("function");
    expect(barrelApi.productApi.getMyScore).toBeTypeOf("function");
    expect(barrelApi.operatorApi.getFlowRuns).toBeTypeOf("function");
    expect(barrelApi.legacyApi.getDashboardOverview).toBeTypeOf("function");
  });

  it("uses explicit API categories in the focused UI components", () => {
    const dashboardSource = readFileSync(new URL("../../components/app/Dashboard.jsx", import.meta.url), "utf8");
    const graphViewSource = readFileSync(new URL("../../components/app/GraphView.jsx", import.meta.url), "utf8");
    const flowConsoleSource = readFileSync(new URL("../../components/platform/FlowEngineConsole.jsx", import.meta.url), "utf8");
    const observabilitySource = readFileSync(new URL("../../components/platform/ObservabilityDashboard.jsx", import.meta.url), "utf8");
    const healthSource = readFileSync(new URL("../../components/platform/HealthDashboard.jsx", import.meta.url), "utf8");

    expect(dashboardSource).toContain('from "../../api/legacy.js"');
    expect(dashboardSource).toContain('from "../../api/product.js"');
    expect(graphViewSource).toContain('from "../../api/legacy.js"');
    expect(flowConsoleSource).toContain('from "../../api/operator.js"');
    expect(observabilitySource).toContain('from "../../api/operator.js"');
    expect(healthSource).toContain('from "../../api/legacy.js"');
  });
});
