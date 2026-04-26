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
            metrics: {
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
            },
            system_state: {
              memory_count: 12,
              active_runs: 2,
              score: 82.5,
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
