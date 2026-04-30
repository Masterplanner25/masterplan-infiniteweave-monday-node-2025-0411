import { expect, test as base, type Page } from "@playwright/test";

const VALID_EMAIL = "testuser@aindy.ai";
const VALID_PASSWORD = "testpass";

function encodeBase64Url(value: string): string {
  return Buffer.from(value, "utf-8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createJwt(payload: Record<string, unknown>): string {
  const header = encodeBase64Url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = encodeBase64Url(JSON.stringify(payload));
  return `${header}.${body}.signature`;
}

type TaskRecord = {
  task_name: string;
  status: "pending" | "in_progress" | "completed";
  time_spent: number;
};

type MasterPlanRecord = {
  id: number;
  version: number;
  version_label: string;
  status: "draft" | "locked" | "active" | "archived";
  is_active: boolean;
  posture?: string;
  created_at?: string;
  locked_at?: string | null;
  anchor_date?: string | null;
  goal_value?: number | null;
  goal_unit?: string | null;
  goal_description?: string | null;
};

export type ApiMockOptions = {
  tasks?: TaskRecord[];
  masterplans?: MasterPlanRecord[];
  loginEmail?: string;
  loginPassword?: string;
  isAdmin?: boolean;
};

export const defaultTasks: TaskRecord[] = [
  { task_name: "Calibrate agent loop", status: "pending", time_spent: 0 },
  { task_name: "Review execution traces", status: "in_progress", time_spent: 900 },
];

export const defaultMasterplans: MasterPlanRecord[] = [
  {
    id: 101,
    version: 3,
    version_label: "V3 NORTHSTAR",
    status: "locked",
    is_active: false,
    posture: "Scale trusted operator workflows",
    created_at: "2026-04-20T12:00:00Z",
    locked_at: "2026-04-21T09:30:00Z",
  },
  {
    id: 102,
    version: 4,
    version_label: "V4 ACTIVE ARC",
    status: "active",
    is_active: true,
    posture: "Increase execution throughput",
    created_at: "2026-04-22T07:45:00Z",
    locked_at: "2026-04-23T07:45:00Z",
  },
];

export async function setupApiMocks(page: Page, options: ApiMockOptions = {}) {
  const tasks = (options.tasks ?? defaultTasks).map((task) => ({ ...task }));
  const masterplans = (options.masterplans ?? defaultMasterplans).map((plan) => ({ ...plan }));
  const loginEmail = options.loginEmail ?? VALID_EMAIL;
  const loginPassword = options.loginPassword ?? VALID_PASSWORD;
  const token = createJwt({
    sub: "u1",
    email: loginEmail,
    username: "testuser",
    is_admin: options.isAdmin ?? false,
    exp: Math.floor(Date.now() / 1000) + 60 * 60,
  });

  await page.addInitScript(
    ({ initialTasks, initialMasterplans, loginEmail: expectedEmail, loginPassword: expectedPassword, token: authToken }) => {
      const tasks = initialTasks.map((task) => ({ ...task }));
      const masterplans = initialMasterplans.map((plan) => ({ ...plan }));
      let scoreMetrics = {
        master_score: 82.5,
        kpis: {
          execution_speed: 85,
          decision_efficiency: 80,
          ai_productivity_boost: 78,
          focus_quality: 84,
          masterplan_progress: 79,
        },
        metadata: {
          confidence: "high",
          calculated_at: "2026-04-26T01:00:00Z",
        },
        message: "Execution systems stable.",
      };
      const agentRuns = [
        {
          run_id: "run-001",
          id: "run-001",
          goal: "Audit masterplan execution drift",
          status: "completed",
          run_type: "masterplan",
          overall_risk: "low",
          created_at: "2026-04-26T10:00:00Z",
          completed_at: "2026-04-26T10:02:30Z",
          steps_completed: 0,
          steps_total: 0,
          plan: { steps: [] },
        },
      ];
      const agentRunSteps: Record<string, unknown[]> = {
        "run-001": [],
      };
      const agentRunEvents: Record<string, unknown[]> = {
        "run-001": [],
      };
      const originalFetch = window.fetch.bind(window);

      const jsonResponse = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });

      const textResponse = (body: string, status = 200) =>
        new Response(body, {
          status,
          headers: { "Content-Type": "text/plain" },
        });

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const request = input instanceof Request ? input : null;
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, window.location.origin);
        const method = (init?.method || request?.method || "GET").toUpperCase();
        const path = url.pathname.replace(/^\/api\b/, "");
        const rawBody = init?.body ?? (request ? await request.clone().text() : "");
        const body = typeof rawBody === "string" && rawBody ? JSON.parse(rawBody) : {};

        if (path === "/auth/login" && method === "POST") {
          if (body?.email === expectedEmail && body?.password === expectedPassword) {
            return jsonResponse({
              access_token: authToken,
              token_type: "bearer",
              user_id: "u1",
              username: "testuser",
            });
          }
          return jsonResponse({ detail: "Invalid credentials" }, 401);
        }

        if (path === "/identity/boot" && method === "GET") {
          return jsonResponse({
            user_id: "u1",
            memory: [],
            runs: [],
            flows: [],
            metrics: scoreMetrics,
            system_state: {
              memory_count: 12,
              active_runs: 2,
              score: scoreMetrics.master_score,
              active_flows: 3,
            },
          });
        }

        if (path === "/dashboard/overview" && method === "GET") {
          return jsonResponse({
            overview: {
              system_timestamp: "2026-04-26T01:00:00Z",
              author_count: 4,
              recent_authors: [
                { id: "a1", name: "Operator One", platform: "web" },
                { id: "a2", name: "Operator Two", platform: "api" },
              ],
              recent_ripples: [{ summary: "Task velocity increased", source_platform: "tasks" }],
            },
          });
        }

        if (path === "/version" && method === "GET") {
          return jsonResponse({
            api_version: "1.0.0",
            min_client_version: "1.0.0",
            breaking_change_policy:
              "MAJOR version increments indicate breaking changes. Clients must re-deploy when the MAJOR version changes. MINOR and PATCH increments are safe for existing clients.",
            changelog_url: null,
          });
        }

        if (path === "/scores/me" && method === "GET") {
          return jsonResponse(scoreMetrics);
        }

        if (path === "/scores/me/history" && method === "GET") {
          return jsonResponse({ history: [] });
        }

        if (path === "/tasks/list" && method === "GET") {
          return jsonResponse(tasks);
        }

        if (path === "/tasks/create" && method === "POST") {
          const taskName = typeof body?.name === "string" ? body.name.trim() : "";
          if (!taskName) {
            return jsonResponse({ detail: "Task name required" }, 400);
          }
          const created = { task_name: taskName, status: "pending", time_spent: 0 };
          tasks.unshift(created);
          return jsonResponse(created, 201);
        }

        if (path === "/tasks/start" && method === "POST") {
          const task = tasks.find((entry) => entry.task_name === body?.name);
          if (task) {
            task.status = "in_progress";
          }
          return jsonResponse(task ?? { detail: "Task not found" }, task ? 200 : 404);
        }

        if (path === "/tasks/complete" && method === "POST") {
          const task = tasks.find((entry) => entry.task_name === body?.name);
          if (task) {
            task.status = "completed";
            task.time_spent = 1800;
            return textResponse(`Task ${task.task_name} completed. TWR score +4.2.`, 200);
          }
          return jsonResponse({ detail: "Task not found" }, 404);
        }

        if (path === "/masterplans/" && method === "GET") {
          return jsonResponse({ plans: masterplans });
        }

        if (path === "/dashboard/health" && method === "GET") {
          return jsonResponse({
            logs: [
              {
                timestamp: "2026-04-26T10:00:00Z",
                status: "healthy",
                avg_latency_ms: 18.4,
              },
              {
                timestamp: "2026-04-26T09:55:00Z",
                status: "healthy",
                avg_latency_ms: 21.1,
              },
            ],
          });
        }

        if (path === "/platform/keys" && method === "GET") {
          return jsonResponse({ keys: [] });
        }

        if (path === "/platform/syscalls" && method === "GET") {
          return jsonResponse({ syscalls: [] });
        }

        if (path === "/agent/runs" && method === "GET") {
          if (url.searchParams.get("status") === "pending_approval") {
            return jsonResponse(agentRuns.filter((run) => run.status === "pending_approval"));
          }

          return jsonResponse(agentRuns);
        }

        if (/^\/agent\/runs\/[^/]+\/steps$/.test(path) && method === "GET") {
          const runId = path.split("/")[3];
          return jsonResponse(agentRunSteps[runId] ?? []);
        }

        if (/^\/agent\/runs\/[^/]+\/events$/.test(path) && method === "GET") {
          const runId = path.split("/")[3];
          return jsonResponse({ run_id: runId, events: agentRunEvents[runId] ?? [] });
        }

        // --- Genesis session lifecycle ---
        if (path === "/genesis/session" && method === "POST") {
          return jsonResponse(
            {
              session_id: "gen-session-001",
              status: "active",
              created_at: new Date().toISOString(),
            },
            201,
          );
        }

        if (path === "/genesis/message" && method === "POST") {
          return jsonResponse({
            session_id: "gen-session-001",
            reply: "I understand your goals. Let me ask — what does success look like in 3 years?",
            synthesis_ready: true,
            status: "active",
          });
        }

        if (path === "/genesis/synthesize" && method === "POST") {
          return jsonResponse({
            session_id: "gen-session-001",
            draft: {
              title: "Strategic Growth Plan",
              vision_statement: "Build a durable SaaS company with compounding distribution.",
              time_horizon_years: 3,
              primary_mechanism: "Product-led growth",
              posture: "Strategic expansion",
              goals: [
                { title: "Increase revenue by 30%", priority: "high" },
                { title: "Launch 2 new products", priority: "medium" },
              ],
              synthesis_ready: true,
            },
            status: "synthesized",
          });
        }

        if (path === "/genesis/lock" && method === "POST") {
          return jsonResponse({
            session_id: "gen-session-001",
            plan_id: "plan-001",
            version: "V5 LOCKED ARC",
            posture: "Strategic expansion",
            status: "locked",
          });
        }

        // --- Freelance orders ---
        if (path === "/freelance/orders" && method === "GET") {
          return jsonResponse([
            {
              id: 1,
              status: "delivered",
              client_name: "Northstar Labs",
              service_type: "Website redesign",
              price: 2500,
              created_at: "2026-04-20T10:00:00Z",
            },
            {
              id: 2,
              status: "in_progress",
              client_name: "Signal Forge",
              service_type: "Mobile app MVP",
              price: 8000,
              created_at: "2026-04-22T14:00:00Z",
            },
          ]);
        }

        if (path === "/freelance/feedback" && method === "GET") {
          return jsonResponse([
            {
              id: 1,
              order_id: 1,
              rating: 5,
              feedback_text: "Fast delivery and clear communication.",
            },
          ]);
        }

        if (path === "/freelance/metrics/latest" && method === "GET") {
          return jsonResponse({
            total_orders: 2,
            delivered: 1,
            total_revenue: 10500,
          });
        }

        if (path === "/agent/tools" && method === "GET") {
          return jsonResponse([
            {
              name: "task.create",
              risk: "low",
              description: "Create a task from a run outcome.",
            },
          ]);
        }

        if (path === "/agent/trust" && method === "GET") {
          return jsonResponse({
            auto_execute_low: false,
            auto_execute_medium: false,
            allowed_auto_grant_tools: [],
          });
        }

        if (path === "/agent/run" && method === "POST") {
          const goal = body?.goal?.trim() || "";
          if (!goal) {
            return jsonResponse({ detail: "goal is required" }, 400);
          }
          const run = {
            run_id: "run-pending-001",
            id: "run-pending-001",
            status: "pending_approval",
            goal,
            objective: goal,
            overall_risk: "medium",
            executive_summary: "Evaluate the submitted goal and propose a plan.",
            steps_total: 2,
            steps_completed: 0,
            plan: {
              steps: [
                { tool: "memory.recall", args: {}, risk_level: "low", description: "Recall relevant context" },
                { tool: "task.create", args: {}, risk_level: "low", description: "Create an action task" },
              ],
              overall_risk: "medium",
              executive_summary: "Recall memory and create a task.",
            },
            events: [],
            trace_id: "trace-pending-001",
            correlation_id: "run_pending-001",
            created_at: new Date().toISOString(),
          };
          const existingIndex = agentRuns.findIndex((entry) => entry.run_id === run.run_id);
          if (existingIndex >= 0) {
            agentRuns.splice(existingIndex, 1);
          }
          agentRuns.unshift(run);
          agentRunSteps[run.run_id] = [];
          agentRunEvents[run.run_id] = [];
          return jsonResponse(run);
        }

        if (/^\/agent\/runs\/[^/]+\/approve$/.test(path) && method === "POST") {
          const runId = path.split("/")[3];
          const index = agentRuns.findIndex((entry) => entry.run_id === runId);
          const goal = index >= 0 ? agentRuns[index].goal : "Test goal";
          const updated = {
            run_id: runId,
            id: runId,
            status: "completed",
            goal,
            objective: goal,
            overall_risk: "medium",
            executive_summary: "Executed successfully.",
            steps_total: 2,
            steps_completed: 2,
            plan: { steps: [], overall_risk: "medium" },
            result: { status: "done" },
            events: [
              { type: "agent.event", event_type: "PLAN_CREATED", timestamp: new Date().toISOString(), payload: { overall_risk: "medium", steps_total: 2 } },
              { type: "agent.event", event_type: "EXECUTION_STARTED", timestamp: new Date().toISOString(), payload: {} },
              { type: "agent.event", event_type: "STEP_EXECUTED", timestamp: new Date().toISOString(), payload: { step_index: 0, tool_name: "memory.recall", status: "success" } },
              { type: "agent.event", event_type: "STEP_EXECUTED", timestamp: new Date().toISOString(), payload: { step_index: 1, tool_name: "task.create", status: "success" } },
            ],
            trace_id: "trace-pending-001",
            created_at: index >= 0 ? agentRuns[index].created_at : new Date().toISOString(),
            completed_at: new Date().toISOString(),
          };
          if (index >= 0) {
            agentRuns[index] = updated;
          } else {
            agentRuns.unshift(updated);
          }
          agentRunEvents[runId] = [
            { id: "ev-1", event_type: "PLAN_CREATED", occurred_at: new Date().toISOString(), payload: { overall_risk: "medium" } },
            { id: "ev-2", event_type: "EXECUTION_STARTED", occurred_at: new Date().toISOString(), payload: {} },
          ];
          agentRunSteps[runId] = [];
          return jsonResponse(updated);
        }

        if (path === "/agent/suggestions" && method === "GET") {
          return jsonResponse([]);
        }

        if (path === "/agent/registry" && method === "GET") {
          return jsonResponse({ agents: [] });
        }

        if (path === "/flows/runs" && method === "GET") {
          return jsonResponse({
            runs: [
              {
                id: "flow-001",
                flow_name: "masterplan_activation",
                status: "success",
                workflow_type: "task_completion",
                created_at: "2026-04-26T10:00:00Z",
                completed_at: "2026-04-26T10:02:30Z",
                current_node: null,
                waiting_for: null,
                error_message: null,
                state: {},
              },
            ],
            total: 1,
          });
        }

        if (/^\/flows\/runs\/[^/]+\/history$/.test(path) && method === "GET") {
          return jsonResponse({ history: [] });
        }

        if (path === "/flows/registry" && method === "GET") {
          return jsonResponse({
            flow_count: 0,
            node_count: 0,
            flows: {},
            nodes: [],
          });
        }

        if (path === "/flows/strategies" && method === "GET") {
          return jsonResponse({ strategies: [], count: 0 });
        }

        if (path === "/automation/logs" && method === "GET") {
          return jsonResponse({ logs: [] });
        }

        if (path === "/automation/scheduler/status" && method === "GET") {
          return jsonResponse({
            running: true,
            job_count: 1,
            jobs: [
              {
                id: "job-001",
                name: "stuck-run watchdog",
                trigger: "interval",
                next_run: "2026-04-26T10:10:00Z",
              },
            ],
          });
        }

        if (path === "/observability/dashboard" && method === "GET") {
          return jsonResponse({
            summary: {
              window_hours: 24,
              avg_latency_ms: 18,
              window_requests: 42,
              window_errors: 0,
              error_rate_pct: 0,
              active_flows: 1,
              loop_events: 2,
              agent_events: 1,
              system_event_total: 3,
              health_status: "healthy",
            },
            request_metrics: {
              recent: [{ path: "/tasks", method: "GET", status_code: 200 }],
              recent_errors: [],
              error_rate_series: [
                { label: "2026-04-26T10:00:00Z", error_rate: 0, errors: 0, requests: 21 },
              ],
            },
            loop_activity: [],
            agent_timeline: [],
            system_events: {
              recent: [],
              counts: {},
            },
            system_health: {
              latest: {
                timestamp: "2026-04-26T10:00:00Z",
                avg_latency_ms: 18,
                status: "healthy",
              },
              logs: [
                {
                  timestamp: "2026-04-26T10:00:00Z",
                  avg_latency_ms: 18,
                  status: "healthy",
                },
              ],
            },
            flows: {
              status_counts: { success: 1 },
              recent: [],
            },
          });
        }

        if (path.startsWith("/observability/") && method === "GET") {
          return jsonResponse({ status: "ok", data: {} });
        }

        if (path.startsWith("/rippletrace/") && method === "GET") {
          return jsonResponse({ traces: [] });
        }

        const activateMatch = path.match(/^\/masterplans\/(\d+)\/activate$/);
        if (activateMatch && method === "POST") {
          const targetId = Number(activateMatch[1]);
          masterplans.forEach((plan) => {
            plan.is_active = plan.id === targetId;
            plan.status = plan.id === targetId ? "active" : plan.status === "active" ? "locked" : plan.status;
          });
          return jsonResponse(masterplans.find((plan) => plan.id === targetId) ?? { detail: "Plan not found" }, 200);
        }

        const projectionMatch = path.match(/^\/masterplans\/(\d+)\/projection$/);
        if (projectionMatch && method === "GET") {
          return jsonResponse({
            eta_confidence: "high",
            velocity: 3.4,
            projected_completion_date: "2026-05-30",
            days_ahead_behind: 4,
            completed_tasks: 17,
            total_tasks: 25,
          });
        }

        const anchorMatch = path.match(/^\/masterplans\/(\d+)\/anchor$/);
        if (anchorMatch && method === "PUT") {
          const targetId = Number(anchorMatch[1]);
          const plan = masterplans.find((entry) => entry.id === targetId);
          if (plan) {
            Object.assign(plan, body);
            return jsonResponse(plan);
          }
          return jsonResponse({ detail: "Plan not found" }, 404);
        }

        if (path === "/health" && method === "GET") {
          return jsonResponse({ status: "ok" });
        }

        if (path === "/scores/me/recalculate" && method === "POST") {
          scoreMetrics = {
            master_score: 88.0,
            kpis: {
              execution_speed: 90,
              decision_efficiency: 86,
              ai_productivity_boost: 85,
              focus_quality: 88,
              masterplan_progress: 91,
            },
            metadata: {
              confidence: "high",
              calculated_at: new Date().toISOString(),
            },
          };
          return jsonResponse(scoreMetrics);
        }

        return originalFetch(input, init);
      };
    },
    {
      initialTasks: tasks,
      initialMasterplans: masterplans,
      loginEmail,
      loginPassword,
      token,
    },
  );
}

export const test = base.extend<{ setupMocks: (options?: ApiMockOptions) => Promise<void> }>({
  setupMocks: async ({ page }, use) => {
    await use(async (options?: ApiMockOptions) => {
      await setupApiMocks(page, options);
    });
  },
});

export { expect, VALID_EMAIL, VALID_PASSWORD };
