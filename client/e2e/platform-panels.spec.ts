import { expect, test } from "./fixtures";
import { LoginPage } from "./pages/LoginPage";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { FlowEnginePage } from "./pages/FlowEnginePage";
import { HealthPage } from "./pages/HealthPage";
import { ExecutionConsolePage } from "./pages/ExecutionConsolePage";
import { AgentRegistryPage } from "./pages/AgentRegistryPage";

async function loginAsAdmin(page, setupMocks) {
  await setupMocks({ isAdmin: true });
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("Health Dashboard renders system health summary", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const healthPage = new HealthPage(page);
  await healthPage.goto();
  await healthPage.expectLoaded();
  await healthPage.expectHealthy();
});

test("Agent Console renders without error", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const agentPage = new AgentConsolePage(page);
  await agentPage.goto();
  await agentPage.expectLoaded();
  await agentPage.expectRunsVisible();
});

test("Flow Engine Console renders without error", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const flowPage = new FlowEnginePage(page);
  await flowPage.goto();
  await flowPage.expectLoaded();
});

test("Approval Inbox renders for admin", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  await page.goto("/platform/approvals");
  await expect(page).toHaveURL(/\/platform\/approvals$/);
  await expect(page.getByRole("heading", { name: "Approval Inbox" })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/approval queue is clear|pending agent runs/i).first()).toBeVisible();
});

test("Observability Dashboard renders for admin", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  await page.goto("/platform/observability");
  await expect(page).toHaveURL(/\/platform\/observability$/);
  await expect(page.getByRole("heading", { name: "Observability Dashboard" })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/system telemetry|error rate tracking/i).first()).toBeVisible();
});

test("Execution Console renders without error", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const execPage = new ExecutionConsolePage(page);
  await execPage.goto();
  await execPage.expectLoaded();
});

test("Agent Registry renders without error", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const registryPage = new AgentRegistryPage(page);
  await registryPage.goto();
  await registryPage.expectLoaded();
});
