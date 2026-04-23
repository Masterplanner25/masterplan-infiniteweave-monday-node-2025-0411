import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, beforeEach, vi } from "vitest";

vi.mock("../_core.js", () => ({
  authRequest: vi.fn(),
}));

import { authRequest } from "../_core.js";
import * as operatorApi from "../operator.js";
import * as legacyApi from "../legacy.js";
import * as platformApi from "../platform.js";
import * as barrelApi from "../../api.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

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
    const dashboardSource = readFileSync(resolve(__dirname, "../../components/app/Dashboard.jsx"), "utf8");
    const graphViewSource = readFileSync(resolve(__dirname, "../../components/app/GraphView.jsx"), "utf8");
    const flowConsoleSource = readFileSync(resolve(__dirname, "../../components/platform/FlowEngineConsole.jsx"), "utf8");
    const observabilitySource = readFileSync(
      resolve(__dirname, "../../components/platform/ObservabilityDashboard.jsx"),
      "utf8",
    );
    const healthSource = readFileSync(resolve(__dirname, "../../components/platform/HealthDashboard.jsx"), "utf8");

    expect(dashboardSource).toContain('from "../../api/legacy.js"');
    expect(dashboardSource).toContain('from "../../api/product.js"');
    expect(graphViewSource).toContain('from "../../api/legacy.js"');
    expect(flowConsoleSource).toContain('from "../../api/operator.js"');
    expect(observabilitySource).toContain('from "../../api/operator.js"');
    expect(healthSource).toContain('from "../../api/legacy.js"');
  });

  it("uses explicit API categories in core data-fetching components", () => {
    const taskSource = readFileSync(resolve(__dirname, "../../components/app/TaskDashboard.jsx"), "utf8");
    const armSource = readFileSync(resolve(__dirname, "../../components/app/ARMAnalyze.jsx"), "utf8");
    const agentSource = readFileSync(resolve(__dirname, "../../components/platform/AgentConsole.jsx"), "utf8");

    expect(taskSource).not.toContain('from "../../api"');
    expect(taskSource).toContain('from "../../api/tasks.js"');
    expect(armSource).not.toContain('from "../../api"');
    expect(armSource).toContain('from "../../api/arm.js"');
    expect(agentSource).not.toContain('from "../../api"');
    expect(agentSource).toContain('from "../../api/agent.js"');
  });
});
